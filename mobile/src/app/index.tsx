import { useRef, useState } from 'react';
import { Button, Platform, Pressable, ScrollView, TextInput, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import {
  useAudioRecorder,
  useAudioRecorderState,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  RecordingPresets,
} from 'expo-audio';
import * as Speech from 'expo-speech';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { useThemePreference } from '@/context/theme-preference';
import { useTheme } from '@/hooks/use-theme';

import { API_URL } from '@/constants/api';
import { BottomTabInset, MaxContentWidth, Spacing } from '@/constants/theme';
import uuid from 'react-native-uuid';

type Message = { role: 'user' | 'assistant'; text: string };

// The backend returns {detail} on errors (expired Google auth, quota, ...);
// surface that instead of a bare status code.
async function errorFromResponse(res: Response): Promise<Error> {
  try {
    const data: { detail?: string } = await res.json();
    if (typeof data.detail === 'string') return new Error(data.detail);
  } catch {}
  return new Error(`Request failed: ${res.status}`);
}

export default function HomeScreen() {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [sending, setSending] = useState(false);
  const { scheme, toggle } = useThemePreference();
  const colors = useTheme();
  const [sessionId] = useState(() => uuid.v4() as string);
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const recorderState = useAudioRecorderState(recorder);
  const scrollRef = useRef<ScrollView>(null);

  async function sendMessage() {
    const text = input.trim();
    if (!text || sending) return;

    setMessages((prev) => [...prev, { role: 'user', text }]);
    setInput('');
    setSending(true);

    try {
      const res = await fetch(`${API_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, message: text }),
      });
      if (!res.ok) {
        throw await errorFromResponse(res);
      }
      const data: { response: string } = await res.json();
      setMessages((prev) => [...prev, { role: 'assistant', text: data.response }]);
    } catch (err) {
      const detail = err instanceof Error ? err.message : String(err);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: `Error: ${detail}` },
      ]);
    } finally {
      setSending(false);
    }
  }

  async function toggleRecording() {
    if (recorderState.isRecording) {
      await recorder.stop();
      // Leaving recording mode on routes speech playback to the quiet
      // earpiece on iOS instead of the speaker.
      await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
      await sendRecording(recorder.uri);
      return;
    }

    Speech.stop(); // don't talk over the user
    const { granted } = await requestRecordingPermissionsAsync();
    if (!granted) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: "Can't record without microphone permission." },
      ]);
      return;
    }

    // iOS rejects allowsRecording: true unless playsInSilentMode is also
    // true in the same call — the two can't be set independently.
    await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
    await recorder.prepareToRecordAsync();
    recorder.record();
  }

  async function sendRecording(uri: string | null) {
    if (!uri || sending) return;
    setSending(true);

    try {
      const formData = new FormData();
      formData.append('session_id', sessionId);

      // The old RN convention of appending {uri, name, type} directly isn't
      // reliably recognized by RN 0.86's FormData/networking implementation
      // ("Unsupported FormDataPart implementation"). Fetching the local URI
      // and appending a real Blob works on both native and web.
      const blob = await (await fetch(uri)).blob();
      const filename = Platform.OS === 'web' ? 'recording.webm' : 'recording.m4a';
      formData.append('audio', blob, filename);

      const res = await fetch(`${API_URL}/voice`, { method: 'POST', body: formData });
      if (!res.ok) {
        throw await errorFromResponse(res);
      }
      const data: { transcript: string; response: string } = await res.json();
      setMessages((prev) => [
        ...prev,
        ...(data.transcript ? [{ role: 'user' as const, text: data.transcript }] : []),
        { role: 'assistant', text: data.response },
      ]);
      Speech.speak(data.response);
    } catch (err) {
      const detail = err instanceof Error ? err.message : String(err);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: `Error: ${detail}` },
      ]);
    } finally {
      setSending(false);
    }
  }

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView style={styles.safeArea}>
        <ThemedView style={styles.heroSection}>
          <ThemedText type="title" style={styles.title}>
            Calendar Agent
          </ThemedText>
        </ThemedView>

        <ScrollView
          ref={scrollRef}
          style={styles.messages}
          contentContainerStyle={styles.messagesContent}
          onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}>
          {messages.map((message, i) => (
            <ThemedView
              key={i}
              type={message.role === 'user' ? 'backgroundSelected' : 'backgroundElement'}
              style={[
                styles.messageBubble,
                message.role === 'user' ? styles.messageBubbleUser : styles.messageBubbleAssistant,
              ]}>
              <ThemedText>{message.text}</ThemedText>
            </ThemedView>
          ))}
        </ScrollView>

        <TextInput
          value={input}
          onChangeText={setInput}
          placeholder="Ask about your calendar."
          placeholderTextColor={colors.textSecondary}
          editable={!sending}
          onSubmitEditing={sendMessage}
          style={[
            styles.input,
            { backgroundColor: colors.backgroundElement, color: colors.text },
          ]}
        />

        <Button title={sending ? 'Sending...' : 'Submit'} onPress={sendMessage} disabled={sending} />

        <Button
          title={recorderState.isRecording ? '⏹ Stop' : '🎙️ Record'}
          onPress={toggleRecording}
          disabled={sending}
        />

        <Pressable onPress={toggle} style={({ pressed }) => pressed && styles.pressed}>
          <ThemedView type="backgroundElement" style={styles.toggleButton}>
            <ThemedText type="small">
              {scheme === 'dark' ? '☀️ Switch to light mode' : '🌙 Switch to dark mode'}
            </ThemedText>
          </ThemedView>
        </Pressable>

      </SafeAreaView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    flexDirection: 'row',
  },
  safeArea: {
    flex: 1,
    paddingHorizontal: Spacing.four,
    alignItems: 'center',
    gap: Spacing.three,
    paddingBottom: BottomTabInset + Spacing.three,
    maxWidth: MaxContentWidth,
  },
  heroSection: {
    alignItems: 'center',
    justifyContent: 'center',
    flex: 1,
    paddingHorizontal: Spacing.four,
    gap: Spacing.four,
  },
  title: {
    textAlign: 'center',
  },
  code: {
    textTransform: 'uppercase',
  },
  stepContainer: {
    gap: Spacing.three,
    alignSelf: 'stretch',
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.four,
    borderRadius: Spacing.four,
  },
  messages: {
    width: '100%',
    flexGrow: 0,
  },
  messagesContent: {
    gap: Spacing.two,
    paddingVertical: Spacing.two,
  },
  messageBubble: {
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two,
    borderRadius: Spacing.three,
    maxWidth: '85%',
  },
  messageBubbleUser: {
    alignSelf: 'flex-end',
  },
  messageBubbleAssistant: {
    alignSelf: 'flex-start',
  },
  input: {
    borderRadius: Spacing.two,
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two,
    width: '100%',
  },
  toggleButton: {
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two,
    borderRadius: Spacing.three,
    alignItems: 'center',
  },
  pressed: {
    opacity: 0.7,
  },
});

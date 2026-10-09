import { useState } from 'react';
import { Button, Pressable, ScrollView, TextInput, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import {
  useAudioRecorder,
  useAudioRecorderState,
  requestRecordingPermissionsAsync,
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

export default function HomeScreen() {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [sending, setSending] = useState(false);
  const { scheme, toggle } = useThemePreference();
  const colors = useTheme();
  const [sessionId] = useState(() => uuid.v4() as string);
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const recorderState = useAudioRecorderState(recorder);

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
        throw new Error(`Request failed: ${res.status}`);
      }
      const data: { response: string } = await res.json();
      setMessages((prev) => [...prev, { role: 'assistant', text: data.response }]);
    } catch (err) {
      const detail = err instanceof Error ? err.message : String(err);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: `Couldn't reach the server: ${detail}` },
      ]);
    } finally {
      setSending(false);
    }
  }

  async function toggleRecording() {
    if (recorderState.isRecording) {
      await recorder.stop();
      await sendRecording(recorder.uri);
      return;
    }

    const { granted } = await requestRecordingPermissionsAsync();
    if (!granted) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: "Can't record without microphone permission." },
      ]);
      return;
    }

    recorder.record();
  }

  async function sendRecording(uri: string | null) {
    if (!uri || sending) return;
    setSending(true);

    try {
      const formData = new FormData();
      formData.append('session_id', sessionId);
      formData.append('audio', { uri, name: 'recording.m4a', type: 'audio/m4a' } as any);

      const res = await fetch(`${API_URL}/voice`, { method: 'POST', body: formData });
      if (!res.ok) {
        throw new Error(`Request failed: ${res.status}`);
      }
      const data: { transcript: string; response: string } = await res.json();
      setMessages((prev) => [
        ...prev,
        { role: 'user', text: data.transcript },
        { role: 'assistant', text: data.response },
      ]);
      Speech.speak(data.response);
    } catch (err) {
      const detail = err instanceof Error ? err.message : String(err);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: `Couldn't reach the server: ${detail}` },
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
            Welcome to&nbsp;Expo
          </ThemedText>
        </ThemedView>

        <ScrollView style={styles.messages} contentContainerStyle={styles.messagesContent}>
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

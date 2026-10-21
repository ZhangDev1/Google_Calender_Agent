import { Platform } from 'react-native';

const PORT = 8000;

// Your machine's current LAN IP (from `ipconfig` -> "IPv4 Address"). Update
// this if it changes, e.g. after reconnecting Wi-Fi or switching networks.
const LAN_IP = '192.168.68.63';

// The backend has to be started with `--host 0.0.0.0` for the LAN_IP case to
// work: `uvicorn api:app --host 0.0.0.0 --port 8000 --reload`. The default
// `127.0.0.1` only accepts connections from this machine, which is fine for
// the web case below but not for a phone/emulator on the network.
export const API_URL =
  Platform.OS === 'web' ? `http://localhost:${PORT}` : `http://${LAN_IP}:${PORT}`;

// Note: if you're testing on the Android *emulator* specifically (not a
// physical device), point the native branch above at `http://10.0.2.2:${PORT}`
// instead — that's the emulator's special alias back to the host machine,
// and LAN_IP won't reach it from inside the emulator's virtual network.

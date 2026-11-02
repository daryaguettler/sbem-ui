import { mount } from 'svelte';
import '@xyflow/svelte/dist/style.css';
import './app.css';
import App from './App.svelte';
import { reopenAfterBackendRestart } from './lib/stores/workspaceStore';

reopenAfterBackendRestart();

const target = document.getElementById('app');

if (!target) {
  throw new Error('app target not found');
}

const app = mount(App, { target });

export default app;

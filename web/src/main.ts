import { mount } from 'svelte';
import '@xyflow/svelte/dist/style.css';
import './app.css';
import App from './App.svelte';

const target = document.getElementById('app');

if (!target) {
  throw new Error('app target not found');
}

const app = mount(App, { target });

export default app;

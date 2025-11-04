import { defineStore } from 'pinia';
import http from '@/utils/http';

export interface ExtensionWidget {
  id: number;
  name: string;
  version: string;
  description?: string;
  author?: string;
  frontend_entry: string;
  frontend_editor?: string;
  config_schema: Record<string, any>;
  file_path: string;
}

export interface Widget {
   id: number; display_id: number; type: 'CLOCK' | 'TEXT' | 'RSS' | string; // Allow extension types
   config: Record<string, any>;
   x: number; y: number; width: number; height: number; z_index: number;
 }

export const useWidgetsStore = defineStore('widgets', {
  state: () => ({
    byDisplayId: {} as Record<number, Widget[]>,
  }),
  actions: {
    authHeaders() {
      const token = localStorage.getItem('authToken') || '';
      return token ? { Authorization: `Bearer ${token}` } : {};
    },
    async fetchAvailableExtensions(): Promise<ExtensionWidget[]> {
      const res = await http.get('/api/extensions/widgets');
      return res.data.items || [];
    },
    list(displayId: number) {
      return this.byDisplayId[displayId] || [];
    },
    async fetchForDisplay(displayId: number) {
      const res = await http.get(`${import.meta.env.VITE_API_BASE_URL}/api/displays/${displayId}/widgets`, { headers: this.authHeaders() });
      this.byDisplayId[displayId] = res.data.items || [];
      return this.byDisplayId[displayId];
    },
    async create(displayId: number, payload: { type: Widget['type']; config: Record<string, any>; x: number; y: number; width: number; height: number; z_index: number; }) {
      // Validate extension widget types
      if (typeof payload.type === 'string' && payload.type.startsWith('extension:')) {
        const extensionId = payload.type.split(':')[1];
        // Check if extension is available (this will be validated on backend too)
        const availableExtensions = await this.fetchAvailableExtensions();
        const extension = availableExtensions.find(ext => ext.id === parseInt(extensionId));
        if (!extension) {
          throw new Error('Extension widget not available');
        }
      }
      const res = await http.post(`${import.meta.env.VITE_API_BASE_URL}/api/displays/${displayId}/widgets`, payload, { headers: this.authHeaders() });
      this.byDisplayId[displayId] = [...(this.byDisplayId[displayId] || []), res.data];
      return res.data as Widget;
    },
    async update(widgetId: number, payload: Partial<Widget>) {
      const res = await http.patch(`${import.meta.env.VITE_API_BASE_URL}/api/widgets/${widgetId}`, payload, { headers: this.authHeaders() });
      const dId = res.data.display_id;
      const arr = this.byDisplayId[dId] || [];
      const idx = arr.findIndex(w => w.id === widgetId);
      if (idx >= 0) arr[idx] = res.data;
      this.byDisplayId[dId] = [...arr];
      return res.data as Widget;
    },
    async remove(widgetId: number) {
      let dId: number | null = null;
      for (const [key, arr] of Object.entries(this.byDisplayId)) {
        const f = arr.find(w => w.id === widgetId);
        if (f) { dId = Number(key); break; }
      }
      await http.delete(`${import.meta.env.VITE_API_BASE_URL}/api/widgets/${widgetId}`, { headers: this.authHeaders() });
      if (dId !== null) this.byDisplayId[dId] = this.byDisplayId[dId].filter(w => w.id !== widgetId);
    },
    async bulkLayout(items: Array<{ id: number; x: number; y: number; width: number; height: number; z_index: number }>) {
      if (!items.length) return { updated: 0 };
      const res = await http.post(`${import.meta.env.VITE_API_BASE_URL}/api/widgets/bulk-layout`, { widgets: items }, { headers: this.authHeaders() });
      return res.data;
    },
  },
});
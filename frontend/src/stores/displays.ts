import { defineStore } from 'pinia';
import http from '@/utils/dynamic-http';

export interface Display {
  id: number;
  title: string;
  slug: string;
  is_public: boolean;
  owner_id?: number;
  owner_username?: string;
}

export const useDisplaysStore = defineStore('displays', {
  state: () => ({
    myDisplays: [] as Display[],
    active: null as Display | null,
  }),
  actions: {
    authHeaders() {
      // No longer needed with shared http interceptors, keep for compatibility
      const token = localStorage.getItem('authToken') || '';
      return token ? { Authorization: `Bearer ${token}` } : {};
    },
    async fetchMy() {
      const res = await http.get(`/api/displays/my`);
      this.myDisplays = res.data.items || [];
    },
    async create(payload: { title: string; slug: string; is_public: boolean }) {
      const res = await http.post(`/api/displays`, payload);
      this.myDisplays.unshift(res.data);
      return res.data as Display;
    },
    async getById(id: number) {
      const res = await http.get(`/api/displays/${id}`);
      this.active = res.data;
      return res.data as Display;
    },
    async update(id: number, payload: Partial<Pick<Display, 'title' | 'slug' | 'is_public'>>) {
      const res = await http.patch(`/api/displays/${id}`, payload);
      this.active = res.data as Display;
      const idx = this.myDisplays.findIndex(d => d.id === id);
      if (idx >= 0) this.myDisplays[idx] = res.data as Display;
      return res.data as Display;
    },
    async remove(id: number) {
      await http.delete(`/api/displays/${id}`);
      this.myDisplays = this.myDisplays.filter(d => d.id !== id);
      if (this.active?.id === id) this.active = null;
    },
  },
});
<template>
  <div class="pages">
    <h1>Pages Management</h1>
    <form @submit.prevent="createPage">
      <input v-model="pageTitle" type="text" placeholder="Page Title" required />
      <EditorContent :editor="editor" />
      <button type="submit" :disabled="isLoading">{{ isLoading ? 'Creating...' : 'Create Page' }}</button>
    </form>

    <h2>Existing Pages</h2>
    <ul>
      <li v-for="page in pages" :key="page.id">
        <h3>{{ page.title }}</h3>
        <button @click="editPage(page)">Edit</button>
        <button @click="deletePage(page.id)" :disabled="isLoading">Delete</button>
      </li>
    </ul>

    <div v-if="editingPage">
      <h2>Edit Page</h2>
      <form @submit.prevent="updatePage">
        <input v-model="editingPage.title" type="text" required />
        <EditorContent :editor="editor" />
        <button type="submit" :disabled="isLoading">{{ isLoading ? 'Updating...' : 'Update Page' }}</button>
      </form>
    </div>

    <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, onMounted, onBeforeUnmount } from 'vue';
import axios from 'axios';
import { Editor, EditorContent } from '@tiptap/vue-3';
import StarterKit from '@tiptap/starter-kit';

export default defineComponent({
  components: { EditorContent },
  setup() {
    const pages = ref<{ id: number; title: string; content: string }[]>([]);
    const pageTitle = ref('');
    const pageContent = ref('');
    const editingPage = ref<{ id: number; title: string; content: string } | null>(null);
    const isLoading = ref(false);
    const errorMessage = ref('');

    const editor = new Editor({
      extensions: [StarterKit],
      content: '',
    });

    const fetchPages = async () => {
      try {
        isLoading.value = true;
        const response = await axios.get(`${import.meta.env.VITE_API_BASE_URL}/pages/read`);
        pages.value = response.data.items;
      } catch (error) {
        errorMessage.value = 'Failed to fetch pages.';
      } finally {
        isLoading.value = false;
      }
    };

    const generateSlug = (title: string) => {
      return title
        .toLowerCase()
        .replace(/\s+/g, '-')
        .replace(/[^a-z0-9-]/g, '');
    };

    const createPage = async () => {
      try {
        isLoading.value = true;
        const slug = generateSlug(pageTitle.value);
        await axios.post(`${import.meta.env.VITE_API_BASE_URL}/pages/create`, {
          title: pageTitle.value,
          content: editor.getHTML(),
          slug: slug,
        });
        pageTitle.value = '';
        editor.commands.setContent('');
        fetchPages();
      } catch (error) {
        errorMessage.value = 'Failed to create page.';
      } finally {
        isLoading.value = false;
      }
    };

    const editPage = (page: { id: number; title: string; content: string }) => {
      editingPage.value = { ...page };
      editor.commands.setContent(page.content);
    };

    const updatePage = async () => {
      try {
        isLoading.value = true;
        if (editingPage.value) {
          await axios.put(`${import.meta.env.VITE_API_BASE_URL}/pages/update`, {
            ...editingPage.value,
            content: editor.getHTML(),
          });
          editingPage.value = null;
          editor.commands.setContent('');
          fetchPages();
        }
      } catch (error) {
        errorMessage.value = 'Failed to update page.';
      } finally {
        isLoading.value = false;
      }
    };

    const deletePage = async (id: number) => {
      try {
        isLoading.value = true;
        await axios.delete(`${import.meta.env.VITE_API_BASE_URL}/pages/delete/${id}`);
        fetchPages();
      } catch (error) {
        errorMessage.value = 'Failed to delete page.';
      } finally {
        isLoading.value = false;
      }
    };

    onMounted(fetchPages);

    onBeforeUnmount(() => {
      editor.destroy();
    });

    return {
      pages,
      pageTitle,
      pageContent,
      editingPage,
      isLoading,
      errorMessage,
      createPage,
      editPage,
      updatePage,
      deletePage,
      editor,
    };
  },
});
</script>

<style scoped>
.pages {
  padding: 20px;
}

.error {
  color: red;
  margin-top: 10px;
}
</style>

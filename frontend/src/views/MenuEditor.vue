<template>
  <div class="container py-5">
    <!-- Page Header -->
    <!-- <header class="text-center mb-5">
      <h1 class="display-4">Menu Editor</h1>
      <p class="lead text-muted">Manage your menu items</p>
    </header> -->

    <div class="row">
      <!-- Menu Editor Section -->
      <div class="col-md-12">
        <div class="card shadow-sm mb-4">
          <div class="card-body">
            <h5 class="card-title">Menu Editor</h5>
            <form @submit.prevent="addMenuItem" class="mb-3">
              <div class="row g-2">
                <div class="col">
                  <input v-model="newMenuItem.name" type="text" placeholder="Menu Name" required class="form-control" />
                </div>
                <div class="col">
                  <input v-model="newMenuItem.path" type="text" placeholder="Menu Path" required class="form-control" />
                </div>
                <div class="col-auto">
                  <button type="submit" class="btn btn-success">Add</button>
                </div>
              </div>
            </form>
            <vue-draggable v-model="menuItems" class="list-group" @end="updateOrderOnDrag">
              <div v-for="item in menuItems" :key="item.id" class="list-group-item d-flex justify-content-between align-items-center">
                <span>
                  <template v-if="item.path === '/auth-action'">
                    <button class="btn btn-primary" @click="handleAuthAction">
                      {{ isLoggedIn ? 'Logout' : 'Login' }}
                    </button>
                  </template>
                  <template v-else>
                    {{ item.name }} ({{ item.path }})
                  </template>
                </span>
                <div>
                  <button @click="editMenuItem(item)" class="btn btn-warning btn-sm">Edit</button>
                  <button @click="deleteMenuItem(item.id)" class="btn btn-danger btn-sm">Delete</button>
                </div>
              </div>
            </vue-draggable>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, onMounted, computed } from 'vue';
import http from '@/utils/http';
import { VueDraggable } from 'vue-draggable-plus';

export default defineComponent({
  name: 'MenuEditor',
  components: { VueDraggable },
  setup() {
    const menuItems = ref<{ id: number; name: string; path: string; order: number }[]>([]);
    const newMenuItem = ref({ name: '', path: '', order: 1 });

    // Computed property to check login status
    const isLoggedIn = computed(() => {
      const token = localStorage.getItem('authToken');
      return !!token && token !== 'null' && token !== 'undefined';
    });

    // Function to handle login/logout action
    const handleAuthAction = () => {
      if (isLoggedIn.value) {
        window.location.href = '/user/logout';
      } else {
        window.location.href = '/user/login';
      }
    };

    const fetchMenuItems = async () => {
      try {
        const res = await http.get(`${import.meta.env.VITE_API_BASE_URL}/menu/read`);
        menuItems.value = res.data.items.sort((a: { order: number }, b: { order: number }) => a.order - b.order);
      } catch (err) {
        console.error('Error loading menu:', err);
      }
    };

    const addMenuItem = async () => {
      const payload = { ...newMenuItem.value }; // Convert to plain object
      console.log('Payload being sent:', payload);
      try {
        const res = await http.post(`${import.meta.env.VITE_API_BASE_URL}/menu/create`, payload);
        menuItems.value.push(res.data);
        newMenuItem.value = { name: '', path: '', order: menuItems.value.length + 1 };
      } catch (err) {
        console.error('Error adding menu item:', err);
      }
    };

    const editMenuItem = async (item: any) => {
      const updatedName = prompt('New name:', item.name);
      const updatedPath = prompt('New path:', item.path);
      const updatedOrder = parseInt(prompt('New order:', item.order.toString()) || item.order.toString(), 10);
      if (updatedName && updatedPath && !isNaN(updatedOrder)) {
        try {
          await http.put(`${import.meta.env.VITE_API_BASE_URL}/menu/update`, {
            id: item.id,
            name: updatedName,
            path: updatedPath,
            order: updatedOrder,
          });
          item.name = updatedName;
          item.path = updatedPath;
          item.order = updatedOrder;
        } catch (err) {
          console.error('Error editing menu item:', err);
        }
      }
    };

    const deleteMenuItem = async (id: number) => {
      try {
        await http.delete(`${import.meta.env.VITE_API_BASE_URL}/menu/delete/${id}`);
        menuItems.value = menuItems.value.filter((i) => i.id !== id);
      } catch (err) {
        console.error('Error deleting menu item:', err);
      }
    };

    const updateOrderOnDrag = async () => {
      menuItems.value.forEach((item, index) => {
        item.order = index + 1;
        try {
          http.put(`${import.meta.env.VITE_API_BASE_URL}/menu/update`, {
            id: item.id,
            name: item.name,
            path: item.path,
            order: item.order,
          });
        } catch (err) {
          console.error('Error updating order:', err);
        }
      });
    };

    onMounted(() => {
      console.log('MenuEditor component mounted');
      fetchMenuItems();
    });

    return { menuItems, newMenuItem, addMenuItem, editMenuItem, deleteMenuItem, updateOrderOnDrag, isLoggedIn, handleAuthAction };
  },
});
</script>

<style scoped>
/* Custom styles for better appearance */
header {
  background-color: #f8f9fa;
  padding: 20px;
  border-radius: 10px;
}
.card {
  border-radius: 10px;
}
.list-group-item {
  border-radius: 5px;
}
</style>

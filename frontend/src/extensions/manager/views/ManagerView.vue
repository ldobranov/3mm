<template>
  <div class="manager-view">
    <h1>Manager Extension</h1>
    <form @submit.prevent="executeTask">
      <div>
        <label for="taskName">Task Name:</label>
        <input id="taskName" v-model="taskName" type="text" required />
      </div>
      <div>
        <label for="parameters">Parameters (JSON):</label>
        <textarea id="parameters" v-model="parameters" required></textarea>
      </div>
      <button type="submit">Execute Task</button>
    </form>
    <div v-if="response">
      <h2>Response:</h2>
      <pre>{{ response }}</pre>
    </div>
  </div>
</template>

<script>
import { ref } from 'vue';
import axios from 'axios';

export default {
  name: 'ManagerView',
  setup() {
    const taskName = ref('');
    const parameters = ref('');
    const response = ref(null);

    const executeTask = async () => {
      try {
        const parsedParameters = JSON.parse(parameters.value);
        const res = await axios.post('/extensions/manager/execute', {
          task_name: taskName.value,
          parameters: parsedParameters,
        });
        response.value = res.data;
      } catch (error) {
        response.value = error.response?.data || error.message;
      }
    };

    return {
      taskName,
      parameters,
      response,
      executeTask,
    };
  },
};
</script>

<style scoped>
.manager-view {
  padding: 20px;
}

form {
  margin-bottom: 20px;
}

label {
  display: block;
  margin-bottom: 5px;
}

input,
textarea {
  width: 100%;
  margin-bottom: 10px;
  padding: 8px;
  border: 1px solid #ccc;
  border-radius: 4px;
}

button {
  padding: 10px 15px;
  background-color: #007bff;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

button:hover {
  background-color: #0056b3;
}
</style>

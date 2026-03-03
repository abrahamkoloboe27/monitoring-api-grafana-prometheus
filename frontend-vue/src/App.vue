<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

// ── State ──────────────────────────────────────────────────────────────────
const tab = ref('items')
const health = ref(null)
const items = ref([])
const loading = ref(false)
const notification = ref(null)

const newItem = ref({ name: '', price: '', in_stock: true })
const compute = ref({ a: '', b: '', operation: 'add' })
const computeResult = ref(null)
const helloName = ref('')
const helloMsg = ref('')

// ── Helpers ────────────────────────────────────────────────────────────────
let notifTimer = null
function notify(msg, type = 'info') {
  clearTimeout(notifTimer)
  notification.value = { msg, type }
  notifTimer = setTimeout(() => (notification.value = null), 4000)
}

const opSymbol = { add: '+', subtract: '−', multiply: '×', divide: '÷' }

// ── API calls ──────────────────────────────────────────────────────────────
async function fetchHealth() {
  try {
    const { data } = await api.get('/health')
    health.value = data
  } catch {
    health.value = { status: 'down' }
  }
}

async function fetchItems() {
  loading.value = true
  try {
    const { data } = await api.get('/items')
    items.value = data.items
  } catch (e) {
    notify(e.response?.data?.detail || e.message, 'error')
  } finally {
    loading.value = false
  }
}

async function addItem() {
  try {
    const { data } = await api.post('/items', {
      name: newItem.value.name,
      price: parseFloat(newItem.value.price),
      in_stock: newItem.value.in_stock,
    })
    newItem.value = { name: '', price: '', in_stock: true }
    notify(`Item "${data.name}" created (ID: ${data.id})`, 'success')
    fetchItems()
  } catch (e) {
    notify(e.response?.data?.detail || e.message, 'error')
  }
}

async function deleteItem(id, name) {
  try {
    await api.delete(`/items/${id}`)
    notify(`Item "${name}" deleted`, 'success')
    fetchItems()
  } catch (e) {
    notify(e.response?.data?.detail || e.message, 'error')
  }
}

async function doCompute() {
  try {
    const { data } = await api.post('/compute', {
      a: parseFloat(compute.value.a),
      b: parseFloat(compute.value.b),
      operation: compute.value.operation,
    })
    computeResult.value = data
  } catch (e) {
    notify(e.response?.data?.detail || e.message, 'error')
  }
}

async function sayHello() {
  try {
    const { data } = await api.get('/hello', {
      params: { name: helloName.value || 'World' },
    })
    helloMsg.value = data.message
  } catch (e) {
    notify(e.response?.data?.detail || e.message, 'error')
  }
}

// ── Lifecycle ──────────────────────────────────────────────────────────────
let healthInterval
onMounted(() => {
  fetchHealth()
  fetchItems()
  healthInterval = setInterval(fetchHealth, 15000)
})
onUnmounted(() => clearInterval(healthInterval))
</script>

<template>
  <div class="app">
    <!-- Header -->
    <header class="header">
      <div class="header-title">
        <span class="logo">💚</span>
        <h1>Monitoring Demo – Vue</h1>
      </div>
      <div :class="['status-badge', health?.status === 'ok' ? 'ok' : 'down']">
        <span class="dot" />
        API {{ health?.status === 'ok' ? 'Online' : 'Offline' }}
      </div>
    </header>

    <!-- Tabs -->
    <nav class="tabs">
      <button
        v-for="t in [
          { id: 'items',   label: '📦 Items'   },
          { id: 'compute', label: '🔢 Compute' },
          { id: 'hello',   label: '👋 Hello'   },
          { id: 'health',  label: '❤️ Health'  },
        ]"
        :key="t.id"
        :class="['tab-btn', { active: tab === t.id }]"
        @click="tab = t.id"
      >
        {{ t.label }}
      </button>
    </nav>

    <!-- Notification -->
    <div v-if="notification" :class="['notification', notification.type]">
      {{ notification.msg }}
      <button class="close-btn" @click="notification = null">×</button>
    </div>

    <!-- Content -->
    <main class="content">

      <!-- Items tab -->
      <section v-if="tab === 'items'" class="panel">
        <h2>Items Management</h2>
        <form class="form row" @submit.prevent="addItem">
          <input v-model="newItem.name" placeholder="Name" required />
          <input
            v-model="newItem.price"
            placeholder="Price (€)"
            type="number"
            step="0.01"
            min="0.01"
            required
          />
          <label class="checkbox-label">
            <input v-model="newItem.in_stock" type="checkbox" />
            In Stock
          </label>
          <button type="submit" class="btn btn-primary">Add Item</button>
        </form>

        <p v-if="loading" class="loading">Loading items…</p>
        <p v-else-if="items.length === 0" class="empty">No items found.</p>
        <table v-else class="table">
          <thead>
            <tr><th>ID</th><th>Name</th><th>Price</th><th>In Stock</th><th>Actions</th></tr>
          </thead>
          <tbody>
            <tr v-for="item in items" :key="item.id">
              <td>{{ item.id }}</td>
              <td>{{ item.name }}</td>
              <td>{{ item.price.toFixed(2) }} €</td>
              <td>{{ item.in_stock ? '✅' : '❌' }}</td>
              <td>
                <button class="btn btn-danger" @click="deleteItem(item.id, item.name)">
                  Delete
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- Compute tab -->
      <section v-if="tab === 'compute'" class="panel">
        <h2>Arithmetic Compute</h2>
        <form class="form compute-form" @submit.prevent="doCompute">
          <input v-model="compute.a" placeholder="A" type="number" required />
          <select v-model="compute.operation">
            <option value="add">+ Add</option>
            <option value="subtract">− Subtract</option>
            <option value="multiply">× Multiply</option>
            <option value="divide">÷ Divide</option>
          </select>
          <input v-model="compute.b" placeholder="B" type="number" required />
          <button type="submit" class="btn btn-primary">Calculate</button>
        </form>
        <div v-if="computeResult" class="result-box">
          <span class="result-expr">
            {{ computeResult.a }} {{ opSymbol[computeResult.operation] }} {{ computeResult.b }}
          </span>
          <span class="result-eq">=</span>
          <span class="result-value">{{ computeResult.result }}</span>
        </div>
      </section>

      <!-- Hello tab -->
      <section v-if="tab === 'hello'" class="panel">
        <h2>Say Hello</h2>
        <form class="form row" @submit.prevent="sayHello">
          <input v-model="helloName" placeholder="Your name (default: World)" />
          <button type="submit" class="btn btn-primary">Greet</button>
        </form>
        <div v-if="helloMsg" class="greeting">{{ helloMsg }} 🎉</div>
      </section>

      <!-- Health tab -->
      <section v-if="tab === 'health'" class="panel">
        <h2>API Health</h2>
        <div v-if="health" class="health-card">
          <div :class="['health-status', health.status === 'ok' ? 'ok' : 'down']">
            {{ health.status === 'ok' ? '✅ API is healthy' : '❌ API is down' }}
          </div>
          <p v-if="health.timestamp" class="health-ts">
            Last checked: {{ new Date(health.timestamp * 1000).toLocaleString() }}
          </p>
          <button class="btn btn-secondary" @click="fetchHealth">Refresh</button>
        </div>
        <p v-else class="loading">Checking…</p>

        <div class="info-box">
          <h3>Monitoring Endpoints</h3>
          <ul>
            <li><code>/metrics</code> – Prometheus metrics for this frontend server</li>
            <li><code>/api/metrics</code> – Prometheus metrics for the FastAPI backend</li>
            <li><code>/api/health</code> – Backend liveness probe</li>
          </ul>
        </div>
      </section>

    </main>

    <footer class="footer">
      Vue Frontend · Port 3002 ·
      <a href="/metrics" target="_blank" rel="noopener noreferrer">View Metrics</a>
    </footer>
  </div>
</template>

<style>
/* ─── Reset & variables ───────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --primary:   #42b883;
  --primary-d: #2d8c5e;
  --danger:    #e05252;
  --success:   #4caf50;
  --bg:        #0d1117;
  --surface:   #161b22;
  --border:    #30363d;
  --text:      #c9d1d9;
  --text-dim:  #8b949e;
  --radius:    8px;
}

body {
  font-family: 'Segoe UI', system-ui, sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
}

.app {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  max-width: 960px;
  margin: 0 auto;
  padding: 0 16px;
}

/* Header */
.header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 20px 0 16px; border-bottom: 1px solid var(--border);
}
.header-title { display: flex; align-items: center; gap: 10px; }
.header-title h1 { font-size: 1.4rem; font-weight: 700; }
.logo { font-size: 1.8rem; }

.status-badge {
  display: flex; align-items: center; gap: 6px;
  font-size: 0.82rem; font-weight: 600;
  padding: 4px 12px; border-radius: 20px; border: 1px solid var(--border);
}
.status-badge.ok   { color: var(--success); border-color: var(--success); }
.status-badge.down { color: var(--danger);  border-color: var(--danger);  }
.dot {
  width: 8px; height: 8px; border-radius: 50%; background: currentColor;
  animation: pulse 2s infinite;
}
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

/* Tabs */
.tabs { display: flex; gap: 4px; padding: 12px 0; border-bottom: 1px solid var(--border); }
.tab-btn {
  background: none; border: 1px solid transparent;
  color: var(--text-dim); padding: 6px 16px; border-radius: var(--radius);
  cursor: pointer; font-size: 0.9rem; transition: all .15s;
}
.tab-btn:hover { color: var(--text); background: var(--surface); }
.tab-btn.active { color: var(--primary); border-color: var(--primary); background: var(--surface); }

/* Notification */
.notification {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 16px; border-radius: var(--radius); margin-top: 12px; font-size: 0.9rem;
}
.notification.success { background: rgba(76,175,80,.15); color: var(--success); }
.notification.error   { background: rgba(224,82,82,.15);  color: var(--danger);  }
.notification.info    { background: rgba(66,184,131,.1);   color: var(--primary); }
.close-btn { background: none; border: none; cursor: pointer; font-size: 1.1rem; color: inherit; padding: 0 4px; }

/* Content */
.content { flex: 1; padding: 20px 0; }
.panel h2 { font-size: 1.15rem; margin-bottom: 16px; }

/* Forms */
.form { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 20px; }
.form input, .form select {
  background: var(--surface); border: 1px solid var(--border);
  color: var(--text); padding: 8px 12px; border-radius: var(--radius);
  font-size: 0.9rem; flex: 1; min-width: 120px;
}
.form input:focus, .form select:focus { outline: none; border-color: var(--primary); }
.checkbox-label { display: flex; align-items: center; gap: 6px; font-size: 0.9rem; cursor: pointer; white-space: nowrap; }
.compute-form input, .compute-form select { max-width: 140px; }

/* Buttons */
.btn {
  padding: 8px 18px; border: none; border-radius: var(--radius);
  font-size: 0.9rem; font-weight: 600; cursor: pointer; transition: opacity .15s; white-space: nowrap;
}
.btn:hover { opacity: 0.85; }
.btn-primary   { background: var(--primary);  color: #000; }
.btn-danger    { background: var(--danger);    color: #fff; padding: 4px 10px; font-size: 0.82rem; }
.btn-secondary { background: var(--surface);   color: var(--text); border: 1px solid var(--border); }

/* Table */
.table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
.table th { text-align: left; padding: 10px 12px; color: var(--text-dim); border-bottom: 1px solid var(--border); }
.table td { padding: 10px 12px; border-bottom: 1px solid var(--border); }
.table tr:last-child td { border-bottom: none; }
.table tr:hover td { background: var(--surface); }
.loading, .empty { color: var(--text-dim); padding: 12px 0; font-size: 0.9rem; }

/* Compute result */
.result-box {
  display: flex; align-items: center; gap: 16px;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 20px 24px; font-size: 1.4rem; margin-top: 8px;
}
.result-expr { color: var(--text-dim); }
.result-eq   { color: var(--text-dim); }
.result-value { color: var(--primary); font-weight: 700; font-size: 1.8rem; }

/* Greeting */
.greeting { font-size: 1.5rem; font-weight: 600; color: var(--primary); padding: 20px; text-align: center; }

/* Health */
.health-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; margin-bottom: 16px; }
.health-status { font-size: 1.1rem; font-weight: 600; margin-bottom: 8px; }
.health-status.ok   { color: var(--success); }
.health-status.down { color: var(--danger);  }
.health-ts { font-size: 0.85rem; color: var(--text-dim); margin-bottom: 12px; }

/* Info box */
.info-box {
  background: var(--surface); border: 1px solid var(--border);
  border-left: 3px solid var(--primary); border-radius: var(--radius); padding: 16px;
}
.info-box h3 { font-size: 0.95rem; margin-bottom: 10px; color: var(--primary); }
.info-box ul { padding-left: 18px; font-size: 0.88rem; color: var(--text-dim); line-height: 1.8; }
.info-box code { color: var(--primary); background: rgba(66,184,131,.1); padding: 1px 5px; border-radius: 3px; }

/* Footer */
.footer { text-align: center; padding: 12px 0; font-size: 0.8rem; color: var(--text-dim); border-top: 1px solid var(--border); margin-top: 8px; }
.footer a { color: var(--primary); text-decoration: none; }
.footer a:hover { text-decoration: underline; }
</style>

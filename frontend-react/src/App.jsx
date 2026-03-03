import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import './App.css'

const api = axios.create({ baseURL: '/api' })

export default function App() {
  const [tab, setTab] = useState('items')
  const [health, setHealth] = useState(null)
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [notification, setNotification] = useState(null)

  const [newItem, setNewItem] = useState({ name: '', price: '', in_stock: true })
  const [compute, setCompute] = useState({ a: '', b: '', operation: 'add' })
  const [computeResult, setComputeResult] = useState(null)
  const [helloName, setHelloName] = useState('')
  const [helloMsg, setHelloMsg] = useState('')

  const notify = (msg, type = 'info') => {
    setNotification({ msg, type })
    setTimeout(() => setNotification(null), 4000)
  }

  const fetchHealth = useCallback(async () => {
    try {
      const { data } = await api.get('/health')
      setHealth(data)
    } catch {
      setHealth({ status: 'down' })
    }
  }, [])

  const fetchItems = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await api.get('/items')
      setItems(data.items)
    } catch (e) {
      notify(e.response?.data?.detail || e.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchHealth()
    fetchItems()
    const interval = setInterval(fetchHealth, 15000)
    return () => clearInterval(interval)
  }, [fetchHealth, fetchItems])

  const addItem = async (e) => {
    e.preventDefault()
    try {
      const { data } = await api.post('/items', {
        ...newItem,
        price: parseFloat(newItem.price),
      })
      setNewItem({ name: '', price: '', in_stock: true })
      notify(`Item "${data.name}" created (ID: ${data.id})`, 'success')
      fetchItems()
    } catch (e) {
      notify(e.response?.data?.detail || e.message, 'error')
    }
  }

  const deleteItem = async (id, name) => {
    try {
      await api.delete(`/items/${id}`)
      notify(`Item "${name}" deleted`, 'success')
      fetchItems()
    } catch (e) {
      notify(e.response?.data?.detail || e.message, 'error')
    }
  }

  const doCompute = async (e) => {
    e.preventDefault()
    try {
      const { data } = await api.post('/compute', {
        a: parseFloat(compute.a),
        b: parseFloat(compute.b),
        operation: compute.operation,
      })
      setComputeResult(data)
    } catch (e) {
      notify(e.response?.data?.detail || e.message, 'error')
    }
  }

  const sayHello = async (e) => {
    e.preventDefault()
    try {
      const { data } = await api.get('/hello', {
        params: { name: helloName || 'World' },
      })
      setHelloMsg(data.message)
    } catch (e) {
      notify(e.response?.data?.detail || e.message, 'error')
    }
  }

  const opSymbol = { add: '+', subtract: '−', multiply: '×', divide: '÷' }

  return (
    <div className="app">
      <header className="header">
        <div className="header-title">
          <span className="logo">⚛️</span>
          <h1>Monitoring Demo – React</h1>
        </div>
        <div className={`status-badge ${health?.status === 'ok' ? 'ok' : 'down'}`}>
          <span className="dot" />
          API {health?.status === 'ok' ? 'Online' : 'Offline'}
        </div>
      </header>

      <nav className="tabs">
        {[
          { id: 'items', label: '📦 Items' },
          { id: 'compute', label: '🔢 Compute' },
          { id: 'hello', label: '👋 Hello' },
          { id: 'health', label: '❤️ Health' },
        ].map(({ id, label }) => (
          <button
            key={id}
            className={`tab-btn${tab === id ? ' active' : ''}`}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </nav>

      {notification && (
        <div className={`notification ${notification.type}`}>
          {notification.msg}
          <button className="close-btn" onClick={() => setNotification(null)}>×</button>
        </div>
      )}

      <main className="content">
        {tab === 'items' && (
          <section className="panel">
            <h2>Items Management</h2>
            <form onSubmit={addItem} className="form row">
              <input
                placeholder="Name"
                value={newItem.name}
                onChange={(e) => setNewItem({ ...newItem, name: e.target.value })}
                required
              />
              <input
                placeholder="Price (€)"
                type="number"
                step="0.01"
                min="0.01"
                value={newItem.price}
                onChange={(e) => setNewItem({ ...newItem, price: e.target.value })}
                required
              />
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={newItem.in_stock}
                  onChange={(e) => setNewItem({ ...newItem, in_stock: e.target.checked })}
                />
                In Stock
              </label>
              <button type="submit" className="btn btn-primary">Add Item</button>
            </form>

            {loading ? (
              <p className="loading">Loading items…</p>
            ) : items.length === 0 ? (
              <p className="empty">No items found.</p>
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Name</th>
                    <th>Price</th>
                    <th>In Stock</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr key={item.id}>
                      <td>{item.id}</td>
                      <td>{item.name}</td>
                      <td>{item.price.toFixed(2)} €</td>
                      <td>{item.in_stock ? '✅' : '❌'}</td>
                      <td>
                        <button
                          className="btn btn-danger"
                          onClick={() => deleteItem(item.id, item.name)}
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        )}

        {tab === 'compute' && (
          <section className="panel">
            <h2>Arithmetic Compute</h2>
            <form onSubmit={doCompute} className="form compute-form">
              <input
                placeholder="A"
                type="number"
                value={compute.a}
                onChange={(e) => setCompute({ ...compute, a: e.target.value })}
                required
              />
              <select
                value={compute.operation}
                onChange={(e) => setCompute({ ...compute, operation: e.target.value })}
              >
                <option value="add">+ Add</option>
                <option value="subtract">− Subtract</option>
                <option value="multiply">× Multiply</option>
                <option value="divide">÷ Divide</option>
              </select>
              <input
                placeholder="B"
                type="number"
                value={compute.b}
                onChange={(e) => setCompute({ ...compute, b: e.target.value })}
                required
              />
              <button type="submit" className="btn btn-primary">Calculate</button>
            </form>
            {computeResult && (
              <div className="result-box">
                <span className="result-expr">
                  {computeResult.a} {opSymbol[computeResult.operation]} {computeResult.b}
                </span>
                <span className="result-eq">=</span>
                <span className="result-value">{computeResult.result}</span>
              </div>
            )}
          </section>
        )}

        {tab === 'hello' && (
          <section className="panel">
            <h2>Say Hello</h2>
            <form onSubmit={sayHello} className="form row">
              <input
                placeholder="Your name (default: World)"
                value={helloName}
                onChange={(e) => setHelloName(e.target.value)}
              />
              <button type="submit" className="btn btn-primary">Greet</button>
            </form>
            {helloMsg && <div className="greeting">{helloMsg} 🎉</div>}
          </section>
        )}

        {tab === 'health' && (
          <section className="panel">
            <h2>API Health</h2>
            {health ? (
              <div className="health-card">
                <div className={`health-status ${health.status === 'ok' ? 'ok' : 'down'}`}>
                  {health.status === 'ok' ? '✅ API is healthy' : '❌ API is down'}
                </div>
                {health.timestamp && (
                  <p className="health-ts">
                    Last checked: {new Date(health.timestamp * 1000).toLocaleString()}
                  </p>
                )}
                <button className="btn btn-secondary" onClick={fetchHealth}>
                  Refresh
                </button>
              </div>
            ) : (
              <p className="loading">Checking…</p>
            )}
            <div className="info-box">
              <h3>Monitoring Endpoints</h3>
              <ul>
                <li><code>/metrics</code> – Prometheus metrics for this frontend server</li>
                <li><code>/api/metrics</code> – Prometheus metrics for the FastAPI backend</li>
                <li><code>/api/health</code> – Backend liveness probe</li>
              </ul>
            </div>
          </section>
        )}
      </main>

      <footer className="footer">
        React Frontend · Port 3001 ·{' '}
        <a href="/metrics" target="_blank" rel="noopener noreferrer">View Metrics</a>
      </footer>
    </div>
  )
}

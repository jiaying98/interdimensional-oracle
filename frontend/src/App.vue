<!-- The main Vue interface stores conversations and connects them to the Oracle API. -->
<script setup>
import { computed, nextTick, onMounted, ref, watch } from "vue"

const apiUrl = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000"
const question = ref("")
const loading = ref(false)
const error = ref("")
const messageList = ref(null)
const sidebarOpen = ref(true)
const requestedTheme = new URLSearchParams(window.location.search).get("theme")
const theme = ref(
  ["dark", "light"].includes(requestedTheme)
    ? requestedTheme
    : localStorage.getItem("oracle-theme") || "dark"
)
const database = ref({ characters: 826, episodes: 51, locations: 126 })
const conversationSearch = ref("")

const saved = JSON.parse(localStorage.getItem("oracle-conversations") || "[]")
const conversations = ref(saved)
const activeId = ref(localStorage.getItem("oracle-active-conversation") || "")

const exploreCards = [
  { icon: "◎", title: "Ask about a character", question: "Who is Rick Sanchez?", count: "826 records" },
  { icon: "⌖", title: "Discover a location", question: "Who lives on the Citadel of Ricks?", count: "126 places" },
  { icon: "▦", title: "Explore an episode", question: "Which episodes feature Summer Smith?", count: "51 episodes" },
  { icon: "⌘", title: "Filter the universe", question: "Which characters are alive?", count: "Status and traits" },
]

function createConversation() {
  const conversation = {
    id: Date.now().toString(),
    title: "New conversation",
    messages: [],
    responseId: null,
    lastEntity: null,
    lastQuery: null,
    updatedAt: Date.now(),
  }
  conversations.value.unshift(conversation)
  activeId.value = conversation.id
  question.value = ""
  error.value = ""
}

if (!conversations.value.length) createConversation()
if (!conversations.value.some((item) => item.id === activeId.value)) {
  activeId.value = conversations.value[0].id
}

const activeConversation = computed(() =>
  conversations.value.find((item) => item.id === activeId.value)
)

const conversationGroups = computed(() => {
  const query = conversationSearch.value.trim().toLowerCase()
  const groups = { Today: [], Yesterday: [], "This week": [], Earlier: [] }
  const today = new Date()
  today.setHours(0, 0, 0, 0)

  for (const conversation of conversations.value) {
    if (query && !conversation.title.toLowerCase().includes(query)) continue
    const age = today.getTime() - new Date(conversation.updatedAt).setHours(0, 0, 0, 0)
    const days = Math.round(age / 86400000)
    const group = days <= 0 ? "Today" : days === 1 ? "Yesterday" : days <= 7 ? "This week" : "Earlier"
    groups[group].push(conversation)
  }

  return Object.entries(groups)
    .filter(([, items]) => items.length)
    .map(([label, items]) => ({ label, items }))
})

watch(
  conversations,
  (value) => localStorage.setItem("oracle-conversations", JSON.stringify(value)),
  { deep: true }
)
watch(activeId, (value) => localStorage.setItem("oracle-active-conversation", value))
watch(
  theme,
  (value) => {
    document.documentElement.dataset.theme = value
    localStorage.setItem("oracle-theme", value)
  },
  { immediate: true }
)

onMounted(async () => {
  try {
    const response = await fetch(`${apiUrl}/api/info`)
    if (response.ok) database.value = await response.json()
  } catch {
    // Keep the last known API counts shown in the welcome screen.
  }
})

async function scrollToBottom() {
  await nextTick()
  messageList.value?.scrollTo({
    top: messageList.value.scrollHeight,
    behavior: "smooth",
  })
}

function selectConversation(id) {
  activeId.value = id
  question.value = ""
  error.value = ""
}

function conversationTime(timestamp) {
  const date = new Date(timestamp)
  const today = new Date()
  if (date.toDateString() === today.toDateString()) {
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
  }
  return date.toLocaleDateString([], { month: "short", day: "numeric" })
}

function deleteConversation(id) {
  conversations.value = conversations.value.filter((item) => item.id !== id)
  if (!conversations.value.length) createConversation()
  if (activeId.value === id) activeId.value = conversations.value[0].id
}

async function sendMessage() {
  const text = question.value.trim()
  const conversation = activeConversation.value
  if (!text || loading.value || !conversation) return

  conversation.messages.push({ role: "user", text })
  if (conversation.title === "New conversation") {
    conversation.title = text.length > 32 ? `${text.slice(0, 32)}...` : text
  }
  conversation.updatedAt = Date.now()
  question.value = ""
  error.value = ""
  loading.value = true
  await scrollToBottom()

  const body = { question: text }
  if (conversation.responseId) body.previous_response_id = conversation.responseId
  if (conversation.lastQuery) body.last_query = conversation.lastQuery
  const previousSource = [...conversation.messages]
    .reverse()
    .find((message) => message.sources?.length === 1)?.sources[0]
  const contextEntity = conversation.lastEntity || previousSource
  if (contextEntity) body.last_entity = contextEntity

  try {
    const response = await fetch(`${apiUrl}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
    if (!response.ok) throw new Error("The server could not process the question.")

    const data = await response.json()
    conversation.messages.push({
      role: "assistant",
      text: data.answer,
      question: text,
      sources: data.table?.type === "aggregate" ? data.sources || [] : data.table ? [] : data.sources || [],
      table: data.table || null,
      visibleRows: 10,
      feedback: null,
    })
    if (data.response_id) conversation.responseId = data.response_id
    if (data.last_entity) conversation.lastEntity = data.last_entity
    if (data.query_context) conversation.lastQuery = data.query_context
    conversation.updatedAt = Date.now()
  } catch (requestError) {
    error.value = requestError.message || "Could not connect to the server."
  } finally {
    loading.value = false
    await scrollToBottom()
  }
}

function useExample(example) {
  question.value = example
  sendMessage()
}

function showMore(message) {
  message.visibleRows = (message.visibleRows || 10) + 20
}

async function sendFeedback(message, helpful) {
  if (message.feedback !== null && message.feedback !== undefined) return
  const conversation = activeConversation.value
  const index = conversation.messages.indexOf(message)
  const previousQuestion = [...conversation.messages.slice(0, index)]
    .reverse()
    .find((item) => item.role === "user")?.text

  try {
    const response = await fetch(`${apiUrl}/api/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        conversation_id: conversation.id,
        question: message.question || previousQuestion || "",
        answer: message.text,
        helpful,
      }),
    })
    if (!response.ok) throw new Error("Could not save feedback.")
    message.feedback = helpful
  } catch (requestError) {
    error.value = requestError.message || "Could not save feedback."
  }
}

function tableColumns(table) {
  if (table.columns) return table.columns
  if (table.type === "episodes") {
    return [
      { key: "name", label: "Episode" },
      { key: "code", label: "Code" },
      { key: "air_date", label: "Air date" },
    ]
  }
  if (table.type === "locations") {
    return [
      { key: "name", label: "Location" },
      { key: "type", label: "Type" },
      { key: "dimension", label: "Dimension" },
    ]
  }
  return [
    { key: "name", label: "Character" },
    { key: "status", label: "Status" },
    { key: "species", label: "Species" },
    { key: "gender", label: "Gender" },
    { key: "location", label: "Current location" },
  ]
}
</script>

<template>
  <div class="app-layout" :class="{ 'sidebar-closed': !sidebarOpen }">
    <aside class="sidebar">
      <div class="sidebar-brand">
        <img src="/logo.jpg" alt="Interdimensional Oracle logo" />
        <div>
          <strong>Interdimensional<br />Oracle</strong>
        </div>
        <span class="brand-spark">✦</span>
      </div>

      <button class="new-chat" type="button" @click="createConversation">
        <span>+</span> New chat
      </button>

      <label class="conversation-search">
        <span>⌕</span>
        <input v-model="conversationSearch" type="search" placeholder="Search conversations" />
      </label>

      <nav class="conversation-list" aria-label="Saved conversations">
        <section v-for="group in conversationGroups" :key="group.label" class="conversation-group">
          <div class="conversation-heading">{{ group.label }}</div>
          <button
            v-for="conversation in group.items"
            :key="conversation.id"
            class="conversation-item"
            :class="{ active: conversation.id === activeId }"
            type="button"
            @click="selectConversation(conversation.id)"
          >
            <span class="conversation-bubble">◯</span>
            <span class="conversation-title">{{ conversation.title }}</span>
            <span class="conversation-time">{{ conversationTime(conversation.updatedAt) }}</span>
            <span
              class="delete-chat"
              role="button"
              aria-label="Delete conversation"
              @click.stop="deleteConversation(conversation.id)"
            >x</span>
          </button>
        </section>
      </nav>

      <div class="sidebar-footer">
        <img src="/logo.jpg" alt="" />
        <div><strong>Oracle Knowledge Base</strong><span>Local conversations</span></div>
      </div>
    </aside>

    <main class="main-panel">
      <header class="topbar">
        <div class="topbar-title">
          <button
            class="icon-button"
            type="button"
            aria-label="Toggle sidebar"
            @click="sidebarOpen = !sidebarOpen"
          >
            <span></span><span></span><span></span>
          </button>
          <strong>Interdimensional Oracle</strong>
          <span class="title-decoration">✦ ▪▪▪▪</span>
        </div>

        <div class="topbar-actions">
          <div class="model-badge">
            <span class="model-chip">▣</span>
            GPT-5.4 mini
          </div>

          <button
            class="theme-switch"
            type="button"
            aria-label="Switch color theme"
            @click="theme = theme === 'dark' ? 'light' : 'dark'"
          >
            <span>☼</span>
            <i><b :class="{ light: theme === 'light' }"></b></i>
            <span>☾</span>
          </button>
        </div>
      </header>

      <div ref="messageList" class="messages" aria-live="polite">
        <section v-if="!activeConversation?.messages.length" class="welcome">
          <div class="welcome-mark"><span></span><img src="/logo.jpg" alt="" /><span></span></div>
          <h1>Welcome to the Oracle</h1>
          <p class="welcome-copy">
            Explore characters, locations, episodes, and the relationships between them.
          </p>
          <p class="database-description">
            A grounded Rick and Morty database with {{ database.characters }} characters,
            {{ database.locations }} locations and {{ database.episodes }} episodes.
            It contains structured facts rather than dialogue or plot summaries.
          </p>

          <div class="examples">
            <button
              v-for="card in exploreCards"
              :key="card.title"
              type="button"
              @click="useExample(card.question)"
            >
              <span class="card-spark">✦</span>
              <span class="card-icon">{{ card.icon }}</span>
              <span class="card-count">{{ card.count }}</span>
              <strong>{{ card.title }}</strong>
            </button>
          </div>
        </section>

        <section v-else class="chat-thread">
          <article
            v-for="(message, index) in activeConversation.messages"
            :key="index"
            class="message-row"
            :class="message.role"
          >
            <div class="message-label">
              {{ message.role === "user" ? "YOU" : "ORACLE" }}
            </div>
            <div class="bubble">
              <p>{{ message.text }}</p>

              <div v-if="message.table" class="result-table-card">
                <div class="table-heading">
                  <strong>
                    <template v-if="message.table.title">{{ message.table.title }}</template>
                    <template v-else>
                      {{ message.table.total }}<template v-if="message.table.match_total > message.table.total"> of {{ message.table.match_total }}</template>
                      {{ message.table.type }}
                    </template>
                  </strong>
                  <span>Database results</span>
                </div>
                <div class="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th v-for="column in tableColumns(message.table)" :key="column.key">
                          {{ column.label }}
                        </th>
                        <th v-if="message.table.type !== 'aggregate'">Source</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="row in message.table.rows.slice(0, message.visibleRows || 10)"
                        :key="row.id || `${row.value}-${index}`"
                      >
                        <td
                          v-for="column in tableColumns(message.table)"
                          :key="column.key"
                        >
                          {{ row[column.key] || "Unknown" }}
                        </td>
                        <td v-if="message.table.type !== 'aggregate'">
                          <a :href="row.url" target="_blank" rel="noreferrer">View</a>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <button
                  v-if="(message.visibleRows || 10) < message.table.rows.length"
                  class="show-more"
                  type="button"
                  @click="showMore(message)"
                >
                  Show 20 more
                </button>
              </div>

              <div v-if="message.sources?.length" class="sources">
                <span>Sources</span>
                <a
                  v-for="source in message.sources"
                  :key="source.url"
                  :href="source.url"
                  target="_blank"
                  rel="noreferrer"
                >
                  {{ source.name }}
                </a>
              </div>

              <div v-if="message.role === 'assistant'" class="feedback-controls">
                <span>{{ message.feedback === null || message.feedback === undefined ? "Was this helpful?" : "Feedback saved" }}</span>
                <button
                  type="button"
                  aria-label="Helpful answer"
                  :class="{ selected: message.feedback === true }"
                  :disabled="message.feedback !== null && message.feedback !== undefined"
                  @click="sendFeedback(message, true)"
                >👍</button>
                <button
                  type="button"
                  aria-label="Not helpful answer"
                  :class="{ selected: message.feedback === false }"
                  :disabled="message.feedback !== null && message.feedback !== undefined"
                  @click="sendFeedback(message, false)"
                >👎</button>
              </div>
            </div>
          </article>

          <article v-if="loading" class="message-row assistant">
            <div class="message-label">ORACLE</div>
            <div class="bubble typing" aria-label="Oracle is thinking">
              <span></span><span></span><span></span>
            </div>
          </article>
        </section>
      </div>

      <footer class="composer-area">
        <p v-if="error" class="error">{{ error }}</p>
        <form class="composer" @submit.prevent="sendMessage">
          <textarea
            v-model="question"
            rows="1"
            maxlength="500"
            placeholder="Ask about a character, episode, or location..."
            aria-label="Question"
            @keydown.enter.exact.prevent="sendMessage"
          ></textarea>
          <button type="submit" :disabled="!question.trim() || loading">
            Send
          </button>
        </form>
        <div class="composer-meta">
          <span>GPT-5.4 mini</span>
          <span>Enter to send / Shift + Enter for a new line</span>
        </div>
      </footer>
    </main>
  </div>
</template>

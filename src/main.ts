import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'
import './style.css'

type CountItem = {
  name: string
  count: number
}

type SlotSummary = {
  sampleCount: number
  awayCount: number
  excludedCount: number
  activeDurationSeconds: number
  topProcesses: CountItem[]
  topTitles: CountItem[]
  topTitleTokens: CountItem[]
}

type WorkInterval = {
  slotStart: string
  slotEnd: string
  status: 'pending' | 'confirmed'
  predictedText: string
  predictedCandidates: string[]
  confirmedText: string | null
  summary: SlotSummary
  snoozeUntil: string | null
  lastPromptAt: string | null
  promptCount: number
}

type SampleOverview = {
  capturedAt: string
  windowTitle: string
  processName: string
  classification: 'active' | 'away' | 'excluded'
}

type SettingsDto = {
  excludedProcesses: string[]
  excludedTitleKeywords: string[]
  autostartEnabled: boolean
  retentionDays: number
}

type Snapshot = {
  intervals: WorkInterval[]
  pendingPrompt: WorkInterval | null
  currentSample: SampleOverview | null
  settings: SettingsDto
  currentSlotStart: string
  nextPromptAt: string
}

type SettingsInput = {
  excludedProcesses: string[]
  excludedTitleKeywords: string[]
  autostartEnabled: boolean
}

type AppView = 'history' | 'settings'

const app = document.querySelector<HTMLDivElement>('#app')

if (!app) {
  throw new Error('App root not found')
}

const state: {
  snapshot: Snapshot | null
  view: AppView
  promptSlotStart: string | null
  historyDrafts: Map<string, string>
} = {
  snapshot: null,
  view: 'history',
  promptSlotStart: null,
  historyDrafts: new Map(),
}

const formatDateTime = (value: string) =>
  new Intl.DateTimeFormat('ja-JP', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))

const formatEndTime = (value: string) =>
  new Intl.DateTimeFormat('ja-JP', {
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))

const formatSlot = (interval: WorkInterval) =>
  `${formatDateTime(interval.slotStart)} - ${formatEndTime(interval.slotEnd)}`

const formatDuration = (seconds: number) => `${Math.round(seconds / 60)}分`

const formatStatus = (sample: SampleOverview | null) => {
  if (!sample) {
    return 'まだサンプルがありません'
  }

  if (sample.classification === 'away') {
    return '離席または不明を記録中'
  }

  if (sample.classification === 'excluded') {
    return '除外対象を記録中'
  }

  return `${sample.processName} / ${sample.windowTitle || 'タイトルなし'}`
}

const setDraft = (slotStart: string, value: string) => {
  state.historyDrafts.set(slotStart, value)
}

const getDraft = (interval: WorkInterval) =>
  state.historyDrafts.get(interval.slotStart) ??
  interval.confirmedText ??
  interval.predictedText

const summaryList = (items: CountItem[], emptyText: string) => {
  if (items.length === 0) {
    return `<span class="muted">${emptyText}</span>`
  }

  return items
    .map((item) => `<span class="pill">${item.name}<strong>${item.count}</strong></span>`)
    .join('')
}

const renderPromptDialog = () => {
  const prompt =
    (state.promptSlotStart &&
      state.snapshot?.intervals.find((interval) => interval.slotStart === state.promptSlotStart)) ||
    null

  if (!prompt) {
    return `
      <dialog id="prompt-dialog">
        <form method="dialog" class="dialog-shell">
          <header class="dialog-header">
            <div>
              <p class="eyebrow">30分確認</p>
              <h2>確認待ちの作業はありません</h2>
            </div>
            <button class="icon-button" value="cancel" aria-label="閉じる">×</button>
          </header>
        </form>
      </dialog>
    `
  }

  const draft = getDraft(prompt)
  const candidates = prompt.predictedCandidates
    .map(
      (candidate) =>
        `<button type="button" class="candidate-chip" data-candidate="${candidate}">${candidate}</button>`,
    )
    .join('')

  return `
    <dialog id="prompt-dialog" aria-labelledby="prompt-title">
      <form method="dialog" class="dialog-shell">
        <header class="dialog-header">
          <div>
            <p class="eyebrow">30分確認</p>
            <h2 id="prompt-title">${formatSlot(prompt)}</h2>
          </div>
          <button class="icon-button" value="cancel" aria-label="閉じる">×</button>
        </header>
        <div class="dialog-body">
          <p class="body-copy">直近30分の履歴から候補を作成しました。必要に応じて書き換えて確定してください。</p>
          <label class="field">
            <span>作業内容</span>
            <textarea id="prompt-textarea" rows="5">${draft}</textarea>
          </label>
          <section class="candidate-section" aria-label="代替候補">
            <h3>代替候補</h3>
            <div class="chip-row">${candidates}</div>
          </section>
          <section class="summary-grid" aria-label="集計">
            <article>
              <h3>主なプロセス</h3>
              <div class="pill-row">${summaryList(prompt.summary.topProcesses, '集計なし')}</div>
            </article>
            <article>
              <h3>主なウィンドウ</h3>
              <div class="pill-row">${summaryList(prompt.summary.topTitles, '集計なし')}</div>
            </article>
          </section>
        </div>
        <footer class="dialog-footer">
          <button type="button" class="secondary-button" id="snooze-button">5分後に再通知</button>
          <button type="button" class="primary-button" id="confirm-button">確定する</button>
        </footer>
      </form>
    </dialog>
  `
}

const renderHistory = () => {
  const intervals = state.snapshot?.intervals ?? []

  return `
    <section class="panel-stack">
      ${intervals
        .map((interval) => {
          const draft = getDraft(interval)
          const statusClass = interval.status === 'confirmed' ? 'status-confirmed' : 'status-pending'

          return `
            <article class="interval-card">
              <header class="interval-header">
                <div>
                  <p class="slot-label">${formatSlot(interval)}</p>
                  <span class="status-badge ${statusClass}">${interval.status === 'confirmed' ? '確定済み' : '未確定'}</span>
                </div>
                <div class="interval-meta">
                  <span>収集 ${interval.summary.sampleCount}件</span>
                  <span>稼働 ${formatDuration(interval.summary.activeDurationSeconds)}</span>
                </div>
              </header>
              <div class="field">
                <span>作業内容</span>
                <textarea data-history-slot="${interval.slotStart}" rows="3">${draft}</textarea>
              </div>
              <div class="detail-grid">
                <section>
                  <h3>予測</h3>
                  <p>${interval.predictedText}</p>
                </section>
                <section>
                  <h3>代替候補</h3>
                  <div class="chip-row">
                    ${interval.predictedCandidates
                      .map(
                        (candidate) =>
                          `<button type="button" class="candidate-chip" data-history-candidate="${interval.slotStart}::${candidate}">${candidate}</button>`,
                      )
                      .join('')}
                  </div>
                </section>
              </div>
              <div class="summary-grid">
                <article>
                  <h3>主なプロセス</h3>
                  <div class="pill-row">${summaryList(interval.summary.topProcesses, '集計なし')}</div>
                </article>
                <article>
                  <h3>主なタイトル語</h3>
                  <div class="pill-row">${summaryList(interval.summary.topTitleTokens, '集計なし')}</div>
                </article>
              </div>
              <footer class="card-footer">
                ${interval.snoozeUntil ? `<span class="muted">再通知予定: ${formatDateTime(interval.snoozeUntil)}</span>` : '<span class="muted">再通知設定なし</span>'}
                <button type="button" class="primary-button compact-button" data-save-slot="${interval.slotStart}">保存</button>
              </footer>
            </article>
          `
        })
        .join('')}
    </section>
  `
}

const renderSettings = () => {
  const settings = state.snapshot?.settings

  if (!settings) {
    return ''
  }

  return `
    <section class="panel-stack">
      <article class="settings-card">
        <header>
          <p class="eyebrow">設定</p>
          <h2>収集と自動起動</h2>
        </header>
        <label class="checkbox-row">
          <input id="autostart-checkbox" type="checkbox" ${settings.autostartEnabled ? 'checked' : ''} />
          <span>Windows ログイン時に自動起動する</span>
        </label>
        <p class="muted">3秒ごとの生サンプルは ${settings.retentionDays} 日で自動削除されます。</p>
      </article>
      <article class="settings-card">
        <h2>除外するプロセス名</h2>
        <p class="muted">1行に1件。例: KeePassXC.exe</p>
        <textarea id="excluded-processes" rows="6">${settings.excludedProcesses.join('\n')}</textarea>
      </article>
      <article class="settings-card">
        <h2>除外するタイトル語</h2>
        <p class="muted">部分一致で除外します。例: パスワード</p>
        <textarea id="excluded-titles" rows="6">${settings.excludedTitleKeywords.join('\n')}</textarea>
      </article>
      <div class="settings-actions">
        <button type="button" class="primary-button" id="save-settings-button">設定を保存</button>
      </div>
    </section>
  `
}

const syncDialogState = () => {
  const dialog = document.querySelector<HTMLDialogElement>('#prompt-dialog')

  if (!dialog) {
    return
  }

  if (state.promptSlotStart) {
    if (!dialog.open) {
      dialog.showModal()
    }
  } else if (dialog.open) {
    dialog.close()
  }
}

const render = () => {
  if (!state.snapshot) {
    app.innerHTML = `
      <main class="shell loading-shell">
        <p>読み込み中...</p>
      </main>
    `
    return
  }

  app.innerHTML = `
    <main class="shell">
      <header class="topbar">
        <div>
          <p class="eyebrow">Work Pulse Checker</p>
          <h1>30分ごとの作業記録</h1>
          <p class="body-copy">現在: ${formatStatus(state.snapshot.currentSample)}</p>
        </div>
        <div class="topbar-meta">
          <span>現在枠: ${formatDateTime(state.snapshot.currentSlotStart)}</span>
          <span>次回確認: ${formatDateTime(state.snapshot.nextPromptAt)}</span>
        </div>
      </header>
      <nav class="tabs" aria-label="表示切替">
        <button type="button" class="${state.view === 'history' ? 'tab is-active' : 'tab'}" data-view="history">履歴</button>
        <button type="button" class="${state.view === 'settings' ? 'tab is-active' : 'tab'}" data-view="settings">設定</button>
      </nav>
      ${state.view === 'history' ? renderHistory() : renderSettings()}
      ${renderPromptDialog()}
    </main>
  `

  wireInteractiveElements()
  syncDialogState()
}

const closePrompt = () => {
  state.promptSlotStart = null
  syncDialogState()
}

const confirmInterval = async (slotStart: string, text: string, fromPrompt: boolean) => {
  await invoke('confirm_interval', { slotStart, text, fromPrompt })
  await refreshSnapshot()
  if (fromPrompt) {
    closePrompt()
  }
}

const wireInteractiveElements = () => {
  document.querySelectorAll<HTMLButtonElement>('[data-view]').forEach((button) => {
    button.addEventListener('click', () => {
      state.view = button.dataset.view as AppView
      render()
    })
  })

  document.querySelectorAll<HTMLTextAreaElement>('[data-history-slot]').forEach((textarea) => {
    textarea.addEventListener('input', () => {
      setDraft(textarea.dataset.historySlot!, textarea.value)
    })
  })

  document.querySelectorAll<HTMLButtonElement>('[data-save-slot]').forEach((button) => {
    button.addEventListener('click', async () => {
      const slotStart = button.dataset.saveSlot!
      const value =
        document.querySelector<HTMLTextAreaElement>(`textarea[data-history-slot="${slotStart}"]`)?.value ??
        ''
      await confirmInterval(slotStart, value.trim(), false)
    })
  })

  document.querySelectorAll<HTMLButtonElement>('[data-history-candidate]').forEach((button) => {
    button.addEventListener('click', () => {
      const data = button.dataset.historyCandidate
      if (!data) {
        return
      }

      const separatorIndex = data.indexOf('::')
      const slotStart = data.slice(0, separatorIndex)
      const candidate = data.slice(separatorIndex + 2)
      const target = document.querySelector<HTMLTextAreaElement>(`textarea[data-history-slot="${slotStart}"]`)

      if (target) {
        target.value = candidate
        setDraft(slotStart, candidate)
      }
    })
  })

  document.querySelectorAll<HTMLButtonElement>('[data-candidate]').forEach((button) => {
    button.addEventListener('click', () => {
      const target = document.querySelector<HTMLTextAreaElement>('#prompt-textarea')
      if (target && button.dataset.candidate) {
        target.value = button.dataset.candidate
        if (state.promptSlotStart) {
          setDraft(state.promptSlotStart, target.value)
        }
      }
    })
  })

  document.querySelector<HTMLTextAreaElement>('#prompt-textarea')?.addEventListener('input', (event) => {
    if (!state.promptSlotStart) {
      return
    }

    setDraft(state.promptSlotStart, (event.target as HTMLTextAreaElement).value)
  })

  document.querySelector<HTMLButtonElement>('#confirm-button')?.addEventListener('click', async () => {
    if (!state.promptSlotStart) {
      return
    }

    const value = document.querySelector<HTMLTextAreaElement>('#prompt-textarea')?.value.trim() ?? ''
    await confirmInterval(state.promptSlotStart, value, true)
  })

  document.querySelector<HTMLButtonElement>('#snooze-button')?.addEventListener('click', async () => {
    if (!state.promptSlotStart) {
      return
    }

    await invoke('snooze_interval', { slotStart: state.promptSlotStart, minutes: 5 })
    await refreshSnapshot()
    closePrompt()
  })

  document.querySelector<HTMLDialogElement>('#prompt-dialog')?.addEventListener('close', () => {
    if (state.promptSlotStart) {
      closePrompt()
    }
  })

  document.querySelector<HTMLButtonElement>('#save-settings-button')?.addEventListener('click', async () => {
    const input: SettingsInput = {
      excludedProcesses:
        document
          .querySelector<HTMLTextAreaElement>('#excluded-processes')
          ?.value.split(/\r?\n/)
          .map((line) => line.trim())
          .filter(Boolean) ?? [],
      excludedTitleKeywords:
        document
          .querySelector<HTMLTextAreaElement>('#excluded-titles')
          ?.value.split(/\r?\n/)
          .map((line) => line.trim())
          .filter(Boolean) ?? [],
      autostartEnabled:
        document.querySelector<HTMLInputElement>('#autostart-checkbox')?.checked ?? true,
    }

    await invoke('save_settings', { input })
    await refreshSnapshot()
  })
}

const refreshSnapshot = async () => {
  state.snapshot = await invoke<Snapshot>('get_snapshot')
  render()
}

const bindBackendEvents = async () => {
  await listen<WorkInterval>('work-prompt', async (event) => {
    state.promptSlotStart = event.payload.slotStart
    state.view = 'history'
    await refreshSnapshot()
  })

  await listen<{ view: AppView }>('navigate', (event) => {
    state.view = event.payload.view
    render()
  })
}

await bindBackendEvents()
await refreshSnapshot()

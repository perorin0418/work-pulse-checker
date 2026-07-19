import { invoke } from '@tauri-apps/api/core'

const params = new URLSearchParams(window.location.search)
const initialSeconds = Number(params.get('seconds')) || 30

let secondsLeft = initialSeconds

const secondsEl = document.querySelector<HTMLDivElement>('#seconds')!

const render = () => {
  secondsEl.textContent = String(secondsLeft)
}

const openPromptNow = async () => {
  try {
    await invoke('open_prompt_now')
  } catch (error) {
    console.error('failed to open prompt', error)
  }
}

render()

const timerId = window.setInterval(() => {
  secondsLeft -= 1
  render()
  if (secondsLeft <= 0) {
    window.clearInterval(timerId)
    void openPromptNow()
  }
}, 1000)

document.body.addEventListener('click', () => {
  window.clearInterval(timerId)
  void openPromptNow()
})

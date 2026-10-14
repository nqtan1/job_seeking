import '@testing-library/jest-dom/vitest'

// jsdom has no modal <dialog>: mark it open so its content is reachable by role and text.
HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) {
  this.setAttribute('open', '')
}
HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) {
  this.removeAttribute('open')
}

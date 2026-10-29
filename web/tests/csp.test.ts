/// <reference types="node" />
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'

// The signature picture is a signed storage URL: Hosting's CSP must let <img> load it.
describe('Hosting CSP', () => {
  it('allows signed storage URLs for images and PDF frames', () => {
    const cfg = JSON.parse(readFileSync('../firebase.json', 'utf8'))
    const csp: string = cfg.hosting.headers[0].headers.find(
      (h: { key: string }) => h.key === 'Content-Security-Policy',
    ).value
    for (const dir of ['img-src', 'frame-src'])
      expect(csp.split(';').find((d) => d.trim().startsWith(dir))).toContain(
        'https://storage.googleapis.com',
      )
  })
})

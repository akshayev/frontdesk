/** Vitest setup (D-039): unmount rendered trees between tests (no Vitest globals). */
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(() => cleanup())

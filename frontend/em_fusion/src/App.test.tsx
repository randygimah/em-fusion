import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'

import App from './App'

test('renders the starter app while the first EM Fusion slice is being planned', () => {
  render(<App />)

  expect(screen.getByRole('heading', { name: /get started/i })).toBeInTheDocument()
})

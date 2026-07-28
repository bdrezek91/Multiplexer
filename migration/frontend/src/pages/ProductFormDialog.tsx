import { useState, type FormEvent } from 'react'
import {
  Alert,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  MenuItem,
  Stack,
  TextField,
} from '@mui/material'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createProduct, updateProduct } from '../api/products'
import { ApiError } from '../api/client'
import type { Product } from '../types'

interface Props {
  open: boolean
  onClose: () => void
  product: Product | null // null = tworzenie nowego produktu
}

export function ProductFormDialog({ open, onClose, product }: Props) {
  const queryClient = useQueryClient()
  const isEditing = product !== null

  const [kod, setKod] = useState(product?.kod ?? '')
  const [nazwa, setNazwa] = useState(product?.nazwa ?? '')
  const [jm, setJm] = useState(product?.jm ?? 'SZT')
  const [grupa, setGrupa] = useState(product?.grupa ?? '')
  const [status, setStatus] = useState(product?.status ?? 'generyczny')
  const [aliasyText, setAliasyText] = useState(product?.aliasy.join(', ') ?? '')
  const [kolorDomniemany, setKolorDomniemany] = useState(product?.kolor_domniemany ?? false)
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: async () => {
      const aliasy = aliasyText
        .split(',')
        .map((a) => a.trim())
        .filter(Boolean)
      // warianty_magazynowe nie sa (jeszcze) edytowalne w tym formularzu - przy edycji
      // przekazujemy niezmienioną wartosc, zeby PUT (pelna zamiana, patrz RAPORT_ETAP_4.md)
      // przypadkiem ich nie skasowal.
      const payload = {
        nazwa,
        jm,
        grupa,
        status,
        atrybuty: product?.atrybuty ?? {},
        kolor_domniemany: kolorDomniemany,
        aliasy,
        warianty_magazynowe: product?.warianty_magazynowe ?? null,
      }
      if (isEditing) {
        return updateProduct(product.kod, payload)
      }
      return createProduct({ ...payload, kod })
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['products'] })
      onClose()
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.detail : 'Nie udało się zapisać produktu')
    },
  })

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    mutation.mutate()
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <form onSubmit={handleSubmit}>
        <DialogTitle>{isEditing ? `Edytuj produkt: ${product.kod}` : 'Nowy produkt'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {error && <Alert severity="error">{error}</Alert>}
            <TextField
              label="Kod"
              value={kod}
              onChange={(e) => setKod(e.target.value)}
              required
              disabled={isEditing}
              helperText={isEditing ? 'Kodu nie można zmienić po utworzeniu' : undefined}
            />
            <TextField label="Nazwa" value={nazwa} onChange={(e) => setNazwa(e.target.value)} required />
            <Stack direction="row" spacing={2}>
              <TextField label="Jednostka miary" value={jm} onChange={(e) => setJm(e.target.value)} sx={{ flex: 1 }} />
              <TextField
                select
                label="Status"
                value={status}
                onChange={(e) => setStatus(e.target.value)}
                sx={{ flex: 1 }}
              >
                <MenuItem value="generyczny">generyczny</MenuItem>
                <MenuItem value="archiwalny">archiwalny</MenuItem>
              </TextField>
            </Stack>
            <TextField label="Grupa" value={grupa} onChange={(e) => setGrupa(e.target.value)} />
            <TextField
              label="Aliasy (oddzielone przecinkami)"
              value={aliasyText}
              onChange={(e) => setAliasyText(e.target.value)}
              multiline
              minRows={2}
            />
            <FormControlLabel
              control={
                <Checkbox checked={kolorDomniemany} onChange={(e) => setKolorDomniemany(e.target.checked)} />
              }
              label="Kolor domniemany (biały, gdy nie podano)"
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>Anuluj</Button>
          <Button type="submit" variant="contained" disabled={mutation.isPending}>
            {mutation.isPending ? 'Zapisywanie...' : 'Zapisz'}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  )
}

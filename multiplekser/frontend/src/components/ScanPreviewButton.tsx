import { useEffect, useRef, useState } from 'react'
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Stack, Typography } from '@mui/material'
import ImageIcon from '@mui/icons-material/Image'
import { getDocumentFile } from '../api/documents'
import { ApiError } from '../api/client'

// Podgląd wewnątrz panelu: bez tworzenia pustej karty about:blank.
// Tymczasowe adresy blob są zwalniane po zmianie strony i zamknięciu.
export function ScanPreviewButton({ documentId, pageCount = 1 }: { documentId: string; pageCount?: number }) {
  const [open, setOpen] = useState(false)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [preview, setPreview] = useState<{ url: string; mime: string; filename: string } | null>(null)
  const requestId = useRef(0)

  useEffect(() => () => { requestId.current += 1 }, [])
  useEffect(() => {
    if (!preview) return
    return () => URL.revokeObjectURL(preview.url)
  }, [preview])

  const loadPage = async (nextPage: number) => {
    const current = ++requestId.current
    setPage(nextPage)
    setLoading(true)
    setError(null)
    setPreview(null)
    try {
      const { blob, filename } = await getDocumentFile(documentId, nextPage)
      if (current !== requestId.current) return
      if (blob.size === 0) throw new Error('Skan jest pusty')
      const url = URL.createObjectURL(blob)
      setPreview({
        url,
        mime: blob.type,
        filename: filename ?? ('wydawka-strona-' + nextPage),
      })
    } catch (err) {
      if (current !== requestId.current) return
      setError(err instanceof ApiError ? err.detail : 'Nie udało się pobrać skanu. Spróbuj ponownie.')
    } finally {
      if (current === requestId.current) setLoading(false)
    }
  }

  const close = () => {
    requestId.current += 1
    setOpen(false)
    setPreview(null)
    setError(null)
    setLoading(false)
  }

  return (
    <>
      <Button variant="outlined" startIcon={<ImageIcon />} onClick={() => {
        setOpen(true)
        void loadPage(1)
      }}>
        Zobacz skan
      </Button>
      <Dialog open={open} onClose={close} maxWidth="xl" fullWidth>
        <DialogTitle>Oryginalny skan — strona {page} z {pageCount}</DialogTitle>
        <DialogContent dividers sx={{ minHeight: '60vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          {loading && <Typography>Wczytywanie skanu…</Typography>}
          {error && <Alert severity="error" sx={{ width: '100%' }}>{error}</Alert>}
          {!loading && preview?.mime.startsWith('image/') && (
            <Box component="img" src={preview.url} alt={'Wydawka — strona ' + page}
              sx={{ maxWidth: '100%', maxHeight: '75vh', objectFit: 'contain' }} />
          )}
          {!loading && preview?.mime === 'application/pdf' && (
            <Box component="iframe" title="Podgląd skanu PDF" src={preview.url}
              sx={{ border: 0, width: '100%', height: '75vh' }} />
          )}
          {!loading && preview && !preview.mime.startsWith('image/') && preview.mime !== 'application/pdf' && (
            <Typography>Podgląd tego formatu nie jest dostępny. Pobierz oryginalny plik poniżej.</Typography>
          )}
        </DialogContent>
        <DialogActions sx={{ justifyContent: 'space-between', px: 2 }}>
          <Stack direction="row" spacing={1}>
            <Button disabled={loading || page <= 1} onClick={() => { void loadPage(page - 1) }}>
              Poprzednia
            </Button>
            <Button disabled={loading || page >= pageCount} onClick={() => { void loadPage(page + 1) }}>
              Następna
            </Button>
          </Stack>
          <Stack direction="row" spacing={1}>
            <Button disabled={!preview || loading} component="a" href={preview?.url} download={preview?.filename}>
              Pobierz oryginał
            </Button>
            <Button onClick={close}>Zamknij</Button>
          </Stack>
        </DialogActions>
      </Dialog>
    </>
  )
}

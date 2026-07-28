import { useRef, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import UploadFileIcon from '@mui/icons-material/UploadFile'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { listDocuments, uploadDocument } from '../api/documents'
import { ApiError } from '../api/client'
import { StatusChip } from '../components/StatusChip'
import { useAuth } from '../auth/AuthContext'

export function DocumentsPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [file, setFile] = useState<File | null>(null)
  const [magazyn, setMagazyn] = useState('')
  const [error, setError] = useState<string | null>(null)

  const { data: documents, isLoading } = useQuery({
    queryKey: ['documents'],
    queryFn: listDocuments,
    // Odswiezanie listy co kilka sekund, zeby statusy "w kolejce"/"przetwarzanie" aktualizowaly
    // sie bez recznego odswiezania strony (przetwarzanie dzieje sie w tle - Celery, patrz Etap 7).
    refetchInterval: 5000,
  })

  const uploadMutation = useMutation({
    mutationFn: () => {
      if (!file) throw new Error('Wybierz plik')
      return uploadDocument(file, magazyn || undefined)
    },
    onSuccess: (created) => {
      void queryClient.invalidateQueries({ queryKey: ['documents'] })
      setFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
      navigate(`/documents/${created.id}`)
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.detail : 'Nie udalo sie wyslac dokumentu')
    },
  })

  const handleUpload = () => {
    setError(null)
    uploadMutation.mutate()
  }

  const magazynyDostepne = user?.magazyny_dostepne ?? []
  const isAdmin = user?.rola === 'admin'

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        Dokumenty
      </Typography>

      <Paper sx={{ p: 2, mb: 3 }}>
        <Typography variant="subtitle1" gutterBottom>
          Wyslij nowy skan
        </Typography>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}
        <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
          <Button variant="outlined" component="label" startIcon={<UploadFileIcon />}>
            {file ? file.name : 'Wybierz plik'}
            <input
              ref={fileInputRef}
              type="file"
              hidden
              accept="image/*,application/pdf"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </Button>
          {isAdmin ? (
            <TextField
              label="Magazyn (opcjonalnie)"
              value={magazyn}
              onChange={(e) => setMagazyn(e.target.value)}
              sx={{ minWidth: 220 }}
            />
          ) : (
            <TextField
              select
              label="Magazyn (opcjonalnie)"
              value={magazyn}
              onChange={(e) => setMagazyn(e.target.value)}
              sx={{ minWidth: 220 }}
              disabled={magazynyDostepne.length === 0}
              helperText={magazynyDostepne.length === 0 ? 'Brak przypisanych magazynow' : undefined}
            >
              <MenuItem value="">Bez magazynu</MenuItem>
              {magazynyDostepne.map((m) => (
                <MenuItem key={m} value={m}>
                  {m}
                </MenuItem>
              ))}
            </TextField>
          )}
          <Button
            variant="contained"
            onClick={handleUpload}
            disabled={!file || uploadMutation.isPending}
          >
            {uploadMutation.isPending ? 'Wysylanie...' : 'Wyslij i rozpoznaj'}
          </Button>
        </Stack>
      </Paper>

      <TableContainer component={Paper}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Plik</TableCell>
              <TableCell>Numer projektu</TableCell>
              <TableCell>Magazyn</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Utworzono</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={5}>Ladowanie...</TableCell>
              </TableRow>
            )}
            {!isLoading && (documents ?? []).length === 0 && (
              <TableRow>
                <TableCell colSpan={5}>Brak dokumentow - wyslij pierwszy skan powyzej</TableCell>
              </TableRow>
            )}
            {(documents ?? []).map((doc) => (
              <TableRow key={doc.id} hover sx={{ cursor: 'pointer' }} onClick={() => navigate(`/documents/${doc.id}`)}>
                <TableCell>{doc.original_filename}</TableCell>
                <TableCell>{doc.numer_projektu ?? '-'}</TableCell>
                <TableCell>{doc.magazyn ?? '-'}</TableCell>
                <TableCell>
                  <StatusChip status={doc.status} />
                </TableCell>
                <TableCell>{new Date(doc.created_at).toLocaleString('pl-PL')}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  )
}

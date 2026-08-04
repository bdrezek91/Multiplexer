import { useRef, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  FormHelperText,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material'
import UploadFileIcon from '@mui/icons-material/UploadFile'
import PhotoCameraIcon from '@mui/icons-material/PhotoCamera'
import CloseIcon from '@mui/icons-material/Close'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { listDocuments, uploadDocument } from '../api/documents'
import { ApiError } from '../api/client'
import { DzialChip } from '../components/DzialChip'
import { StatusChip } from '../components/StatusChip'
import { KNOWN_MAGAZYNY, magazynLabel } from '../constants'
import { compressImageForUpload } from '../utils/compressImage'

export function DocumentsPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const cameraInputRef = useRef<HTMLInputElement>(null)

  // Zwykle jeden plik (skan PDF albo jedno zdjecie), czasem dwa-trzy - papierowa wydawka
  // rozlozona na kilku osobnych zdjeciach z telefonu, bo nie zmiescila sie na jednym
  // (w przeciwienstwie do wielostronicowego PDF-a) - patrz historia czatu. Backend laczy
  // wszystkie pliki w jeden dokument/jedna rozpiske (patrz prompt.py, WIELE OBRAZOW).
  //
  // Aparat na telefonie robi jedno zdjecie na wywolanie (input z "capture"), wiec zdjecia sie
  // DOKLADAJA do listy przy kazdym wywolaniu "Zrob zdjecie" - konwersja/wyslanie startuje
  // dopiero po recznym kliknieciu "Wyslij i rozpoznaj", nigdy automatycznie po zdjeciu.
  const [files, setFiles] = useState<File[]>([])
  const [magazyn, setMagazyn] = useState('')
  const [error, setError] = useState<string | null>(null)

  const addFiles = async (newFiles: FileList | null) => {
    if (!newFiles || newFiles.length === 0) return
    // Kompresja PRZED dodaniem do listy - patrz utils/compressImage.ts (nie traci jakosci
    // widzianej przez AI, tylko skraca czas przesylu z telefonu, zwlaszcza na wolnym LTE).
    const compressed = await Promise.all(Array.from(newFiles).map((f) => compressImageForUpload(f)))
    setFiles((prev) => [...prev, ...compressed])
  }

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index))
  }

  const { data: documents, isLoading } = useQuery({
    queryKey: ['documents'],
    queryFn: listDocuments,
    // Odswiezanie listy co kilka sekund, zeby statusy "w kolejce"/"przetwarzanie" aktualizowaly
    // sie bez recznego odswiezania strony (przetwarzanie dzieje sie w tle - Celery, patrz Etap 7).
    refetchInterval: 5000,
  })

  const uploadMutation = useMutation({
    mutationFn: () => {
      if (files.length === 0) throw new Error('Wybierz plik')
      return uploadDocument(files, magazyn || undefined)
    },
    onSuccess: (created) => {
      void queryClient.invalidateQueries({ queryKey: ['documents'] })
      setFiles([])
      if (fileInputRef.current) fileInputRef.current.value = ''
      if (cameraInputRef.current) cameraInputRef.current.value = ''
      navigate(`/documents/${created.id}`)
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.detail : 'Nie udało się wysłać dokumentu')
    },
  })

  const handleUpload = () => {
    setError(null)
    uploadMutation.mutate()
  }

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        Dokumenty
      </Typography>

      <Paper sx={{ p: 2, mb: 3 }}>
        <Typography variant="subtitle1" gutterBottom>
          Wyślij nowy skan
        </Typography>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}
        <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
          <Button variant="outlined" component="label" startIcon={<PhotoCameraIcon />}>
            Zrób zdjęcie
            <input
              ref={cameraInputRef}
              type="file"
              hidden
              accept="image/*"
              capture="environment"
              onChange={(e) => {
                addFiles(e.target.files)
                e.target.value = ''
              }}
            />
          </Button>
          <Button variant="outlined" component="label" startIcon={<UploadFileIcon />}>
            Wybierz plik(i)
            <input
              ref={fileInputRef}
              type="file"
              hidden
              multiple
              accept="image/*,application/pdf"
              onChange={(e) => {
                addFiles(e.target.files)
                e.target.value = ''
              }}
            />
          </Button>
          <Box>
            <ToggleButtonGroup
              exclusive
              value={magazyn || null}
              onChange={(_, next: string | null) => setMagazyn(next ?? '')}
              size="small"
            >
              {KNOWN_MAGAZYNY.map((m) => (
                <ToggleButton key={m.value} value={m.value}>
                  {m.label}
                </ToggleButton>
              ))}
            </ToggleButtonGroup>
            <FormHelperText>Magazyn (opcjonalnie) - kliknij ponownie, żeby odznaczyć</FormHelperText>
          </Box>
          <Button
            variant="contained"
            onClick={handleUpload}
            disabled={files.length === 0 || uploadMutation.isPending}
          >
            {uploadMutation.isPending ? 'Wysyłanie...' : 'Zatwierdź i wyślij do rozpoznania'}
          </Button>
        </Stack>

        {files.length > 0 && (
          <Box sx={{ mt: 2 }}>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              {files.map((f, i) => (
                <Chip
                  key={`${f.name}-${i}`}
                  label={f.name}
                  onDelete={() => removeFile(i)}
                  deleteIcon={<CloseIcon aria-label={`Usuń ${f.name}`} />}
                />
              ))}
            </Stack>
            <FormHelperText>
              {files.length === 1
                ? '1 zdjęcie/plik wybrany - dodaj kolejne albo zatwierdź, żeby wysłać do rozpoznania'
                : `${files.length} zdjęć/plików = kolejne strony JEDNEJ wydawki - dodaj kolejne albo zatwierdź, żeby wysłać do rozpoznania`}
            </FormHelperText>
          </Box>
        )}
      </Paper>

      <TableContainer component={Paper}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Plik</TableCell>
              <TableCell>Numer projektu</TableCell>
              <TableCell>Magazyn</TableCell>
              <TableCell>Dział</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Utworzono</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={6}>Ładowanie...</TableCell>
              </TableRow>
            )}
            {!isLoading && (documents ?? []).length === 0 && (
              <TableRow>
                <TableCell colSpan={6}>Brak dokumentów - wyślij pierwszy skan powyżej</TableCell>
              </TableRow>
            )}
            {(documents ?? []).map((doc) => (
              <TableRow key={doc.id} hover sx={{ cursor: 'pointer' }} onClick={() => navigate(`/documents/${doc.id}`)}>
                <TableCell>{doc.original_filename}</TableCell>
                <TableCell>{doc.numer_projektu ?? '-'}</TableCell>
                <TableCell>{doc.magazyn ? magazynLabel(doc.magazyn) : '-'}</TableCell>
                <TableCell>
                  <DzialChip dzial={doc.dzial} confidence={doc.dzial_confidence} />
                </TableCell>
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

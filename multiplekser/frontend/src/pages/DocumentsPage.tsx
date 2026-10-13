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
import { getClaudeUsage, listDocuments, uploadDocument } from '../api/documents'
import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../api/client'
import { DzialChip } from '../components/DzialChip'
import { StatusChip } from '../components/StatusChip'
import { KNOWN_MAGAZYNY, magazynLabel } from '../constants'
import { compressImageForUpload } from '../utils/compressImage'

export function DocumentsPage() {
  const { user } = useAuth()
  const isAdmin = user?.rola === 'admin'
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
  const [ocrEngine, setOcrEngine] = useState<'auto_v3' | 'standard' | 'claude_jev_test'>('auto_v3')
  const [showDiagnostics, setShowDiagnostics] = useState(false)
  const [claudeDzial, setClaudeDzial] = useState<'elektryka' | 'hydraulika'>('elektryka')
  const [error, setError] = useState<string | null>(null)
  const [compressionWarning, setCompressionWarning] = useState<string | null>(null)
  const [preparingBatches, setPreparingBatches] = useState(0)
  const compressionQueueRef = useRef<Promise<void>>(Promise.resolve())
  const isPreparingFiles = preparingBatches > 0

  const addFiles = (newFiles: FileList | null) => {
    if (!newFiles || newFiles.length === 0) return
    const selectedFiles = Array.from(newFiles)
    setPreparingBatches((count) => count + 1)

    // Kolejne wywolania aparatu sa przetwarzane w kolejnosci wyboru. Bez kolejki mniejsze
    // zdjecie nr 2 moglo skonczyc kompresje przed zdjeciem nr 1 i trafic do OCR jako pierwsze.
    compressionQueueRef.current = compressionQueueRef.current
      .catch(() => undefined)
      .then(async () => {
        const fallbackNames: string[] = []
        const compressed = await Promise.all(selectedFiles.map(async (file) => {
          try {
            return await compressImageForUpload(file, 2600, 0.9, () => fallbackNames.push(file.name))
          } catch {
            fallbackNames.push(file.name)
            return file
          }
        }))
        setFiles((prev) => [...prev, ...compressed])
        if (fallbackNames.length > 0) {
          const names = [...new Set(fallbackNames)].join(', ')
          setCompressionWarning(
            `Nie udało się skompresować: ${names}. Zostanie wysłany oryginalny plik.`,
          )
        }
      })
      .finally(() => setPreparingBatches((count) => Math.max(0, count - 1)))
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

  const { data: claudeUsage } = useQuery({
    queryKey: ['claude-usage'],
    queryFn: getClaudeUsage,
    enabled: isAdmin,
    refetchInterval: 15000,
    retry: false,
  })

  const uploadMutation = useMutation({
    mutationFn: () => {
      if (files.length === 0) throw new Error('Wybierz plik')
      return uploadDocument(files, magazyn || undefined, ocrEngine, ocrEngine === 'claude_jev_test' ? claudeDzial : undefined)
    },
    onSuccess: (created) => {
      void queryClient.invalidateQueries({ queryKey: ['documents'] })
      setFiles([])
      setCompressionWarning(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
      if (cameraInputRef.current) cameraInputRef.current.value = ''

      // Po uploadzie robimy pelne wejscie na swiezo utworzony dokument zamiast miekkiej
      // nawigacji SPA. W Chrome zdarzalo sie, ze bezposredni navigate() zaraz po POST 202
      // zostawial pusty ekran do recznego F5, mimo ze backend poprawnie przetwarzal wydawke.
      // Hard navigation pobiera od razu aktualny stan queued/processing/done z serwera i nie
      // wysyla pliku ponownie - POST zakonczyl sie juz powyzej.
      const target = `/documents/${created.id}`
      if (import.meta.env.MODE === 'test') {
        navigate(target)
      } else {
        window.location.assign(target)
      }
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.detail : 'Nie udało się wysłać dokumentu')
    },
  })

  const handleUpload = () => {
    if (isPreparingFiles) return
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
        {compressionWarning && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            {compressionWarning}
          </Alert>
        )}
        {isAdmin && claudeUsage && (
          <Alert severity={
            !claudeUsage.daemon_online ? 'error'
              : claudeUsage.last_status !== 'done' && claudeUsage.last_error_kind === 'limit' ? 'warning'
                : 'info'
          } sx={{ mb: 2 }}>
            <Typography variant="subtitle2" fontWeight={700}>
              Claude Pro + JEV — {claudeUsage.daemon_online ? 'usługa działa na VPS' : 'usługa niedostępna'}
            </Typography>
            <Typography variant="body2">
              Wydawki przetworzone: <strong>{claudeUsage.documents_done}</strong>
              {' · '}W toku: <strong>{claudeUsage.documents_waiting}</strong>
              {' · '}Z błędem: <strong>{claudeUsage.documents_error}</strong>.
              {' '}Odczyty Claude ostatnie 24 h: <strong>{claudeUsage.jobs_24h}</strong>
              {' '}({claudeUsage.pages_24h} stron); ostatnie 7 dni: <strong>{claudeUsage.jobs_7d}</strong>
              {' '}({claudeUsage.pages_7d} stron).
              {claudeUsage.avg_seconds !== null && (
                <> Średni czas samego OCR: <strong>{claudeUsage.avg_seconds.toFixed(1)} s</strong>.</>
              )}
            </Typography>
            {claudeUsage.last_status !== 'done' && claudeUsage.last_error_kind === 'limit' && (
              <Typography variant="body2" color="warning.main">
                Claude zgłosił wyczerpanie limitu. Nowe testy poczekają na odnowienie limitu.
              </Typography>
            )}
            <Typography variant="caption" display="block">
              Dokładny pozostały limit pięciogodzinny/tygodniowy: Claude → Settings → Usage.
              Ten panel mierzy zrealizowane wywołania od uruchomienia monitoringu, nie procent abonamentu.
            </Typography>
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
          <Box sx={{ minWidth: 240 }}>
            <Typography variant="body2" fontWeight={700}>
              {ocrEngine === 'auto_v3' ? 'Multiplekser AUTO' :
                ocrEngine === 'standard' ? 'Diagnostyka: Gemini' : 'Diagnostyka: Claude + JEV'}
            </Typography>
            <FormHelperText>
              {ocrEngine === 'auto_v3'
                ? 'Gemini czyta wydawkę jako pierwszy, a jeśli jest niedostępny — Claude przejmuje OCR. JEV dobiera kody Optimy.'
                : 'Ręcznie wybrany silnik diagnostyczny.'}
            </FormHelperText>
            {isAdmin && (
              <Button size="small" onClick={() => setShowDiagnostics((prev) => !prev)}>
                {showDiagnostics ? 'Ukryj diagnostykę modeli' : 'Diagnostyka modeli'}
              </Button>
            )}
          </Box>
          {isAdmin && showDiagnostics && (
            <Box sx={{ width: '100%' }}>
              <ToggleButtonGroup
                exclusive
                value={ocrEngine}
                onChange={(_, next: 'auto_v3' | 'standard' | 'claude_jev_test' | null) => {
                  if (next) setOcrEngine(next)
                }}
                size="small"
                aria-label="Diagnostyczny wybór silnika OCR"
              >
                <ToggleButton value="auto_v3">AUTO (zalecane)</ToggleButton>
                <ToggleButton value="standard">Gemini</ToggleButton>
                <ToggleButton value="claude_jev_test">Claude + JEV (ręcznie)</ToggleButton>
              </ToggleButtonGroup>
              {ocrEngine === 'claude_jev_test' && (
                <Box sx={{ mt: 1 }}>
                  <ToggleButtonGroup
                    exclusive value={claudeDzial}
                    onChange={(_, next: 'elektryka' | 'hydraulika' | null) => {
                      if (next) setClaudeDzial(next)
                    }}
                    size="small" aria-label="Dział wydawki dla Claude"
                  >
                    <ToggleButton value="elektryka">Elektryka</ToggleButton>
                    <ToggleButton value="hydraulika">Hydraulika</ToggleButton>
                  </ToggleButtonGroup>
                </Box>
              )}
              <FormHelperText>Diagnostyka administratora: tylko na potrzeby porównań silników.</FormHelperText>
            </Box>
          )}
          <Button
            variant="contained"
            onClick={handleUpload}
            disabled={files.length === 0 || isPreparingFiles || uploadMutation.isPending}
          >
            {isPreparingFiles
              ? 'Przygotowywanie plików...'
              : uploadMutation.isPending
                ? 'Wysyłanie...'
                : 'Rozpoznaj wydawkę'}
          </Button>
        </Stack>

        <Alert severity="info" sx={{ mt: 2 }}>
          {ocrEngine === 'auto_v3'
            ? 'AUTO: Gemini → zapasowy Claude → JEV. Nieczytelne pozycje sprawdź na skanie przed importem do Optimy.'
            : 'Tryb diagnostyczny: sprawdź ilości oraz kody z oryginalnym skanem przed importem do Optimy.'}
        </Alert>
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
                <TableCell>
                  {doc.original_filename}
                  {(doc.source_type.startsWith('claude_jev_test_') || doc.source_type === 'auto_v3') && (
                    <Chip size="small" label={doc.source_type === 'auto_v3' ? 'AUTO V3' : 'Claude + JEV · test'} color="info" sx={{ ml: 1 }} />
                  )}
                </TableCell>
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

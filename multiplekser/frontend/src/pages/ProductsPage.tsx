import { useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  IconButton,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material'
import DeleteIcon from '@mui/icons-material/Delete'
import EditIcon from '@mui/icons-material/Edit'
import AddIcon from '@mui/icons-material/Add'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { deleteProduct, listProducts } from '../api/products'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { ProductFormDialog } from './ProductFormDialog'
import type { Dzial, Product } from '../types'

const DZIALY: { value: Dzial; label: string }[] = [
  { value: 'elektryka', label: 'Elektryka' },
  { value: 'hydraulika', label: 'Hydraulika' },
]

export function ProductsPage() {
  const { user } = useAuth()
  const isAdmin = user?.rola === 'admin'
  const queryClient = useQueryClient()

  const [dzial, setDzial] = useState<Dzial>('elektryka')
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(25)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingProduct, setEditingProduct] = useState<Product | null>(null)

  const { data: products, isLoading, error } = useQuery({
    queryKey: ['products', { dzial, search, status, page, rowsPerPage }],
    queryFn: () =>
      listProducts({
        dzial,
        search: search || undefined,
        status: status || undefined,
        limit: rowsPerPage,
        offset: page * rowsPerPage,
      }),
  })

  const deleteMutation = useMutation({
    mutationFn: (kod: string) => deleteProduct(kod, dzial),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['products'] }),
  })

  const openCreateDialog = () => {
    setEditingProduct(null)
    setDialogOpen(true)
  }

  const openEditDialog = (product: Product) => {
    setEditingProduct(product)
    setDialogOpen(true)
  }

  const handleDelete = (kod: string) => {
    if (window.confirm(`Usunąć produkt "${kod}"? Tej operacji nie można cofnąć.`)) {
      deleteMutation.mutate(kod)
    }
  }

  // Backend nie zwraca calkowitej liczby wynikow - "nastepna strona" jest dostepna tylko gdy
  // biezaca strona jest pelna (limit == liczba zwroconych wierszy), inaczej to ostatnia strona.
  const pageItems = products ?? []
  const hasNextPage = pageItems.length === rowsPerPage

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={2}>
        <Stack direction="row" spacing={2} alignItems="center">
          <Typography variant="h5">Katalog produktów</Typography>
          <ToggleButtonGroup
            exclusive
            value={dzial}
            onChange={(_, next: Dzial | null) => {
              if (!next) return
              setDzial(next)
              setPage(0)
            }}
            size="small"
          >
            {DZIALY.map((d) => (
              <ToggleButton key={d.value} value={d.value}>
                {d.label}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
        </Stack>
        {isAdmin && (
          <Button variant="contained" startIcon={<AddIcon />} onClick={openCreateDialog}>
            Nowy produkt
          </Button>
        )}
      </Stack>

      <Stack direction="row" spacing={2} mb={2}>
        <TextField
          label="Szukaj po nazwie"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value)
            setPage(0)
          }}
          sx={{ minWidth: 280 }}
        />
        <TextField
          select
          label="Status"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value)
            setPage(0)
          }}
          sx={{ minWidth: 180 }}
        >
          <MenuItem value="">Wszystkie</MenuItem>
          <MenuItem value="generyczny">generyczny</MenuItem>
          <MenuItem value="archiwalny">archiwalny</MenuItem>
        </TextField>
      </Stack>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error instanceof ApiError ? error.detail : 'Nie udało się pobrać katalogu produktów'}
        </Alert>
      )}

      <TableContainer component={Paper}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Kod</TableCell>
              <TableCell>Nazwa</TableCell>
              <TableCell>Grupa</TableCell>
              <TableCell>JM</TableCell>
              <TableCell>Status</TableCell>
              {isAdmin && <TableCell align="right">Akcje</TableCell>}
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={isAdmin ? 6 : 5}>Ładowanie...</TableCell>
              </TableRow>
            )}
            {!isLoading && pageItems.length === 0 && (
              <TableRow>
                <TableCell colSpan={isAdmin ? 6 : 5}>Brak wyników</TableCell>
              </TableRow>
            )}
            {pageItems.map((product) => (
              <TableRow key={product.kod} hover>
                <TableCell>{product.kod}</TableCell>
                <TableCell>{product.nazwa}</TableCell>
                <TableCell>{product.grupa}</TableCell>
                <TableCell>{product.jm}</TableCell>
                <TableCell>
                  <Chip size="small" label={product.status} color={product.status === 'generyczny' ? 'success' : 'default'} />
                </TableCell>
                {isAdmin && (
                  <TableCell align="right">
                    <IconButton size="small" onClick={() => openEditDialog(product)} aria-label={`Edytuj ${product.kod}`}>
                      <EditIcon fontSize="small" />
                    </IconButton>
                    <IconButton size="small" onClick={() => handleDelete(product.kod)} aria-label={`Usuń ${product.kod}`}>
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <TablePagination
          component="div"
          count={hasNextPage ? -1 : page * rowsPerPage + pageItems.length}
          page={page}
          onPageChange={(_, newPage) => setPage(newPage)}
          rowsPerPage={rowsPerPage}
          onRowsPerPageChange={(e) => {
            setRowsPerPage(parseInt(e.target.value, 10))
            setPage(0)
          }}
          rowsPerPageOptions={[10, 25, 50, 100]}
          labelDisplayedRows={({ from, to }) => `${from}-${to}`}
        />
      </TableContainer>

      {dialogOpen && (
        <ProductFormDialog open={dialogOpen} onClose={() => setDialogOpen(false)} product={editingProduct} dzial={dzial} />
      )}
    </Box>
  )
}

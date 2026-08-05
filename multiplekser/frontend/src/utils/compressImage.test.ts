import { afterEach, describe, expect, it, vi } from 'vitest'
import { compressImageForUpload } from './compressImage'

function fakeFile(name: string, type: string) {
  return new File(['dane'], name, { type })
}

describe('compressImageForUpload', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('nie rusza plikow PDF', async () => {
    const pdf = fakeFile('skan.pdf', 'application/pdf')
    const result = await compressImageForUpload(pdf)
    expect(result).toBe(pdf)
  })

  it('zostawia bez zmian zdjecie ktore juz miesci sie w limicie', async () => {
    vi.stubGlobal('createImageBitmap', vi.fn().mockResolvedValue({ width: 1200, height: 900, close: vi.fn() }))
    const file = fakeFile('male.jpg', 'image/jpeg')
    const result = await compressImageForUpload(file, 2600)
    expect(result).toBe(file)
  })

  it('przeskalowuje zbyt duze zdjecie i zwraca nowy plik JPEG pod tym samym imieniem', async () => {
    vi.stubGlobal('createImageBitmap', vi.fn().mockResolvedValue({ width: 4000, height: 3000, close: vi.fn() }))
    const drawImage = vi.fn()
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
      { drawImage } as unknown as CanvasRenderingContext2D,
    )
    vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation(function (
      this: HTMLCanvasElement,
      cb: BlobCallback,
    ) {
      cb(new Blob(['skompresowane'], { type: 'image/jpeg' }))
    })

    const file = fakeFile('duze.jpg', 'image/jpeg')
    const result = await compressImageForUpload(file, 2600)

    expect(result).not.toBe(file)
    expect(result.name).toBe('duze.jpg')
    expect(result.type).toBe('image/jpeg')
    expect(drawImage).toHaveBeenCalledOnce()
  })

  it('zachowuje proporcje obrazu przy skalowaniu', async () => {
    vi.stubGlobal('createImageBitmap', vi.fn().mockResolvedValue({ width: 4000, height: 2000, close: vi.fn() }))
    const drawImage = vi.fn()
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
      { drawImage } as unknown as CanvasRenderingContext2D,
    )
    let capturedWidth = 0
    let capturedHeight = 0
    vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation(function (
      this: HTMLCanvasElement,
      cb: BlobCallback,
    ) {
      capturedWidth = this.width
      capturedHeight = this.height
      cb(new Blob(['x'], { type: 'image/jpeg' }))
    })

    await compressImageForUpload(fakeFile('panorama.jpg', 'image/jpeg'), 2600)

    expect(capturedWidth).toBe(2600)
    expect(capturedHeight).toBe(1300)
  })

  it('zwraca oryginal gdy createImageBitmap sie nie powiedzie (format nieobslugiwany)', async () => {
    vi.stubGlobal('createImageBitmap', vi.fn().mockRejectedValue(new Error('unsupported')))
    const file = fakeFile('dziwny.jpg', 'image/jpeg')
    const onFallback = vi.fn()
    const result = await compressImageForUpload(file, 2600, 0.9, onFallback)
    expect(result).toBe(file)
    expect(onFallback).toHaveBeenCalledOnce()
  })

  it('zwraca oryginal i zglasza fallback gdy canvas rzuci blad', async () => {
    vi.stubGlobal('createImageBitmap', vi.fn().mockResolvedValue({ width: 4000, height: 3000, close: vi.fn() }))
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(() => {
      throw new Error('canvas failure')
    })
    const file = fakeFile('blad-canvas.jpg', 'image/jpeg')
    const onFallback = vi.fn()

    const result = await compressImageForUpload(file, 2600, 0.9, onFallback)

    expect(result).toBe(file)
    expect(onFallback).toHaveBeenCalledOnce()
  })
})

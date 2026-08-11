// Zmniejsza zdjecie PRZED wyslaniem na serwer (nie dotyczy PDF) - serwer i tak przeskalowuje
// kazdy obraz do tego samego maxSide/quality (patrz backend/app/core/config.py,
// ocr_image_max_side/ocr_image_quality) przed wyslaniem do AI, wiec robienie tego juz w
// przegladarce nie traci ZADNEJ jakosci ostatecznie widzianej przez model - tylko skraca czas
// przesylu z telefonu na serwer (realny przypadek: kilkumegabajtowe zdjecie z aparatu na wolnym
// LTE potrafilo wgrywac sie kilkanascie minut i konczyc bledem 502, patrz historia czatu).
export async function compressImageForUpload(
  file: File,
  maxSide = 2600,
  quality = 0.9,
  onFallback?: (error: unknown) => void,
): Promise<File> {
  if (!file.type.startsWith('image/')) return file // PDF-y wysylane bez zmian

  let bitmap: ImageBitmap | undefined
  try {
    bitmap = await createImageBitmap(file)
    const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height))
    if (scale >= 1) return file // juz wystarczajaco male

    const canvas = document.createElement('canvas')
    canvas.width = Math.round(bitmap.width * scale)
    canvas.height = Math.round(bitmap.height * scale)
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('Przegladarka nie udostepnila kontekstu canvas 2D')
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height)

    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', quality))
    if (!blob) throw new Error('Przegladarka nie utworzyla skompresowanego obrazu')
    return new File([blob], file.name, { type: 'image/jpeg' })
  } catch (error) {
    // Oryginal nadal jest prawidlowym plikiem do uploadu; callback pozwala UI poinformowac,
    // ze wysylka moze potrwac dluzej, zamiast po cichu zgubic wybrana strone.
    onFallback?.(error)
    return file
  } finally {
    bitmap?.close?.()
  }
}

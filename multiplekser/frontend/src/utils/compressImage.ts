// Zmniejsza zdjecie PRZED wyslaniem na serwer (nie dotyczy PDF) - serwer i tak przeskalowuje
// kazdy obraz do tego samego maxSide/quality (patrz backend/app/core/config.py,
// ocr_image_max_side/ocr_image_quality) przed wyslaniem do AI, wiec robienie tego juz w
// przegladarce nie traci ZADNEJ jakosci ostatecznie widzianej przez model - tylko skraca czas
// przesylu z telefonu na serwer (realny przypadek: kilkumegabajtowe zdjecie z aparatu na wolnym
// LTE potrafilo wgrywac sie kilkanascie minut i konczyc bledem 502, patrz historia czatu).
export async function compressImageForUpload(file: File, maxSide = 2600, quality = 0.9): Promise<File> {
  if (!file.type.startsWith('image/')) return file // PDF-y wysylane bez zmian

  let bitmap: ImageBitmap
  try {
    bitmap = await createImageBitmap(file)
  } catch {
    return file // format nieobslugiwany przez createImageBitmap - wyslij oryginal, serwer sobie poradzi
  }

  const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height))
  if (scale >= 1) {
    bitmap.close?.()
    return file // juz wystarczajaco male
  }

  const canvas = document.createElement('canvas')
  canvas.width = Math.round(bitmap.width * scale)
  canvas.height = Math.round(bitmap.height * scale)
  const ctx = canvas.getContext('2d')
  if (!ctx) {
    bitmap.close?.()
    return file
  }
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  bitmap.close?.()

  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', quality))
  if (!blob) return file
  return new File([blob], file.name, { type: 'image/jpeg' })
}

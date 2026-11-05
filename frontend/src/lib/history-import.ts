export const MAX_IMPORT_FILE_SIZE = 5 * 1024 * 1024

type ImportFile = Pick<File, "size" | "text">

export async function importHistoryFile(
  file: ImportFile,
  importJSON: (text: string) => Promise<unknown>
): Promise<void> {
  if (file.size > MAX_IMPORT_FILE_SIZE) {
    throw new Error(
      "This file is too large to import. Maximum allowed size is 5 MiB. Your existing history was not changed."
    )
  }

  const text = await file.text()
  await importJSON(text)
}
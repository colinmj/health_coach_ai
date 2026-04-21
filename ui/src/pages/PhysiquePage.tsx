import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { uploadProgressPhoto, getProgressPhotos, deleteProgressPhoto, type ProgressPhoto } from '@/lib/api'
import { ChevronLeft, ChevronRight, Check, Trash2 } from 'lucide-react'

const CONSENT_KEY = 'physique_consent_v1'

function ConsentBanner({ onAccept }: { onAccept: () => void }) {
  return (
    <div className="rounded-lg border bg-muted/40 px-4 py-4 space-y-3">
      <p className="text-sm text-foreground leading-relaxed">
        Your progress photos are stored securely and privately. When you ask, Coach Donnie can
        review them to give you a visual assessment of your progress — he'll never analyse them
        without your request. You can delete your photos at any time.
      </p>
      <button
        onClick={onAccept}
        className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
      >
        Got it
      </button>
    </div>
  )
}

function PhotoCard({
  photo,
  selected,
  onToggle,
  onDelete,
  selectionFull,
}: {
  photo: ProgressPhoto
  selected: boolean
  onToggle: () => void
  onDelete: () => void
  selectionFull: boolean
}) {
  const [deleting, setDeleting] = useState(false)
  const date = new Date(photo.taken_at).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
  const disabled = selectionFull && !selected

  async function handleDelete(e: React.MouseEvent) {
    e.stopPropagation()
    setDeleting(true)
    try {
      await onDelete()
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div
      onClick={disabled ? undefined : onToggle}
      className={`group relative rounded-lg border overflow-hidden transition-all
        ${selected ? 'ring-2 ring-primary' : ''}
        ${disabled ? 'opacity-40 cursor-default' : 'cursor-pointer hover:opacity-90'}`}
    >
      {selected && (
        <div className="absolute top-1.5 right-1.5 z-10 flex h-5 w-5 items-center justify-center rounded-full bg-primary text-primary-foreground shadow">
          <Check className="h-3 w-3" strokeWidth={3} />
        </div>
      )}
      <img
        src={photo.url}
        alt={date}
        className="w-full object-cover aspect-[3/4]"
      />
      <div className="flex items-center justify-between px-3 py-2">
        <div>
          <p className="text-xs font-medium">{date}</p>
          {photo.notes && (
            <p className="text-xs text-muted-foreground mt-0.5">{photo.notes}</p>
          )}
        </div>
        <button
          onClick={handleDelete}
          disabled={deleting}
          className="opacity-0 group-hover:opacity-100 ml-2 shrink-0 rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-all disabled:opacity-50"
          aria-label="Delete photo"
        >
          {deleting
            ? <div className="h-3.5 w-3.5 animate-spin rounded-full border border-current border-t-transparent" />
            : <Trash2 className="h-3.5 w-3.5" />
          }
        </button>
      </div>
    </div>
  )
}

function TransformationCard({ photo }: { photo: ProgressPhoto }) {
  const date = new Date(photo.taken_at).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
  return (
    <div className="rounded-lg border overflow-hidden">
      <img
        src={photo.url}
        alt={date}
        className="w-full object-cover aspect-[3/4]"
      />
      <div className="px-2 py-1.5">
        <p className="text-xs font-medium">{date}</p>
      </div>
    </div>
  )
}

function TransformationSection({
  selectedPhotos,
  onAnalyze,
}: {
  selectedPhotos: ProgressPhoto[]
  onAnalyze: () => void
}) {
  const sorted = [...selectedPhotos].sort((a, b) =>
    a.taken_at.localeCompare(b.taken_at),
  )

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Transformation</h2>
        {selectedPhotos.length > 0 && (
          <span className="text-xs text-muted-foreground">
            {selectedPhotos.length} / 6 selected
          </span>
        )}
      </div>

      {selectedPhotos.length === 0 ? (
        <div className="flex items-center justify-center rounded-lg border-2 border-dashed border-muted-foreground/25 px-6 py-8 text-center">
          <p className="text-sm text-muted-foreground">
            Select up to 6 photos below to build your transformation timeline
          </p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-3">
            {sorted.map((p) => (
              <TransformationCard key={p.id} photo={p} />
            ))}
          </div>
          {selectedPhotos.length >= 2 && (
            <button
              onClick={onAnalyze}
              className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              Ask Donnie to analyze progress
            </button>
          )}
        </>
      )}
    </div>
  )
}

export function PhysiquePage() {
  const [consentGiven, setConsentGiven] = useState(
    () => localStorage.getItem(CONSENT_KEY) === '1',
  )
  const [takenAt, setTakenAt] = useState(() => new Date().toISOString().slice(0, 10))
  const [notes, setNotes] = useState('')
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successCount, setSuccessCount] = useState<number | null>(null)
  const [page, setPage] = useState(1)
  const [selectedPhotos, setSelectedPhotos] = useState<ProgressPhoto[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()

  const { data: photosPage } = useQuery({
    queryKey: ['progress-photos', page],
    queryFn: () => getProgressPhotos(page),
  })

  const totalPages = photosPage ? Math.ceil(photosPage.total / photosPage.page_size) : 1
  const selectionFull = selectedPhotos.length >= 6

  function acceptConsent() {
    localStorage.setItem(CONSENT_KEY, '1')
    setConsentGiven(true)
  }

  function toggleSelect(photo: ProgressPhoto) {
    setSelectedPhotos((prev) => {
      const isSelected = prev.some((p) => p.id === photo.id)
      if (isSelected) return prev.filter((p) => p.id !== photo.id)
      if (prev.length >= 6) return prev
      return [...prev, photo]
    })
  }

  function handleAnalyze() {
    // Phase 2: dispatch to Donnie via chat
  }

  async function handleDelete(photo: ProgressPhoto) {
    await deleteProgressPhoto(photo.id)
    setSelectedPhotos((prev) => prev.filter((p) => p.id !== photo.id))
    await queryClient.invalidateQueries({ queryKey: ['progress-photos'] })
  }

  async function handleFile(file: File) {
    setError(null)
    setSuccessCount(null)
    setUploading(true)
    try {
      await uploadProgressPhoto(file, `${takenAt}T00:00:00Z`, notes || undefined)
      setTakenAt(new Date().toISOString().slice(0, 10))
      setNotes('')
      setPage(1)
      await queryClient.invalidateQueries({ queryKey: ['progress-photos'] })
      const updated = queryClient.getQueryData<{ total: number }>(['progress-photos', 1])
      setSuccessCount(updated?.total ?? null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
    e.target.value = ''
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-8 space-y-8">
      <div>
        <h1 className="text-xl font-semibold">Physique Progress</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Upload progress photos for Coach Donnie to assess your visual changes over time.
        </p>
      </div>

      {!consentGiven && <ConsentBanner onAccept={acceptConsent} />}

      {consentGiven && (
        <div className="space-y-6">
          {/* Date taken */}
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="photo-date">Date taken</label>
            <input
              id="photo-date"
              type="date"
              value={takenAt}
              max={new Date().toISOString().slice(0, 10)}
              onChange={(e) => setTakenAt(e.target.value)}
              onClick={(e) => (e.currentTarget as HTMLInputElement).showPicker?.()}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring cursor-pointer"
            />
          </div>

          {/* Notes input */}
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="photo-notes">
              Notes <span className="text-muted-foreground font-normal">(optional)</span>
            </label>
            <input
              id="photo-notes"
              type="text"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. End of cut, 12 weeks in"
              className="w-full rounded-md border bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>

          {/* Upload zone */}
          <div
            onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => !uploading && fileInputRef.current?.click()}
            className={`relative flex flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors cursor-pointer select-none
              ${dragging ? 'border-primary bg-primary/5' : 'border-muted-foreground/30 hover:border-muted-foreground/60 hover:bg-muted/30'}
              ${uploading ? 'pointer-events-none opacity-60' : ''}`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={onFileChange}
            />
            {uploading ? (
              <div className="flex flex-col items-center gap-2">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                <span className="text-sm text-muted-foreground">Uploading…</span>
              </div>
            ) : (
              <>
                <svg className="mb-3 h-8 w-8 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
                <p className="text-sm font-medium">Drop photo here or click to upload</p>
                <p className="mt-1 text-xs text-muted-foreground">JPEG, PNG, WebP, or HEIC</p>
              </>
            )}
          </div>

          {error && (
            <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>
          )}

          {successCount !== null && (
            <p className="text-sm text-green-600 dark:text-green-400">
              Photo uploaded. You now have {successCount} photo{successCount !== 1 ? 's' : ''} stored.
            </p>
          )}
        </div>
      )}

      {/* Transformation section */}
      {photosPage && photosPage.total > 0 && (
        <TransformationSection
          selectedPhotos={selectedPhotos}
          onAnalyze={handleAnalyze}
        />
      )}

      {/* All photos */}
      {photosPage && photosPage.total > 0 && (
        <div className="space-y-3">
          <p className="text-sm font-medium text-muted-foreground">
            Photos · tap to select for transformation
          </p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {photosPage.photos.map((p) => (
              <PhotoCard
                key={p.id}
                photo={p}
                selected={selectedPhotos.some((s) => s.id === p.id)}
                onToggle={() => toggleSelect(p)}
                onDelete={() => handleDelete(p)}
                selectionFull={selectionFull}
              />
            ))}
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between pt-1">
              <button
                onClick={() => setPage((p) => p - 1)}
                disabled={page === 1}
                className="flex items-center gap-1 rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted disabled:opacity-40 disabled:pointer-events-none transition-colors"
              >
                <ChevronLeft className="h-4 w-4" /> Prev
              </button>
              <span className="text-xs text-muted-foreground">
                {page} / {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={page === totalPages}
                className="flex items-center gap-1 rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted disabled:opacity-40 disabled:pointer-events-none transition-colors"
              >
                Next <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

import { useQuery } from '@tanstack/react-query'
import { Download, Mic, Video } from 'lucide-react'
import { api, API_TOKEN, type RecordingInfo } from '../api/client'
import { Button } from './ui/button'
import { Card, CardContent, CardHeader, CardTitle } from './ui/card'

interface RecordingPlayerProps {
  sessionId: string
  channel: string | null
  recallRecordingUrl?: string | null
  recordingUrl?: string | null
}

export default function RecordingPlayer({ sessionId, channel, recallRecordingUrl, recordingUrl }: RecordingPlayerProps) {
  // Teams session with a Recall.ai recording URL — show video player
  if (channel === 'teams' && recallRecordingUrl) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Video size={14} className="text-violet-500" /> Teams Recording
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <video controls className="w-full rounded-lg border" src={recallRecordingUrl}>
            Your browser does not support the video element.
          </video>
          <div className="flex justify-end">
            <Button variant="outline" size="sm" className="gap-1.5" asChild>
              <a href={recallRecordingUrl} target="_blank" rel="noopener noreferrer" download>
                <Download size={13} /> Download
              </a>
            </Button>
          </div>
        </CardContent>
      </Card>
    )
  }

  // Teams session without a recording URL — recording not captured
  if (channel === 'teams') {
    return (
      <div className="py-12 text-center space-y-2">
        <Video size={32} className="mx-auto text-muted-foreground/40" />
        <p className="text-sm font-medium text-muted-foreground">No recording available</p>
        <p className="text-xs text-muted-foreground/70">
          Recall.ai recording was not captured for this session.
          Recording must be enabled in your Recall.ai bot configuration.
        </p>
      </div>
    )
  }

  // Phone session — try direct recording_url first, then fetch from Twilio API
  return <PhoneRecordingPlayer sessionId={sessionId} directUrl={recordingUrl} />
}

function PhoneRecordingPlayer({ sessionId, directUrl }: { sessionId: string; directUrl?: string | null }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['recordings', sessionId],
    queryFn: () => api.reports.getRecordings(sessionId),
  })

  if (isLoading) {
    return <p className="text-sm text-muted-foreground py-4">Loading recordings…</p>
  }

  if (isError) {
    // If Twilio API fails but we have a direct URL, fall back to it
    if (directUrl) {
      return <DirectAudioPlayer url={directUrl} label="Phone Recording" />
    }
    return (
      <div className="py-12 text-center space-y-2">
        <Mic size={32} className="mx-auto text-muted-foreground/40" />
        <p className="text-sm font-medium text-muted-foreground">Failed to load recordings</p>
        <p className="text-xs text-muted-foreground/70">Could not reach the Twilio recordings API.</p>
      </div>
    )
  }

  const recordings = data?.recordings ?? []

  // No recordings from Twilio API — try direct URL fallback
  if (recordings.length === 0) {
    if (directUrl) {
      return <DirectAudioPlayer url={directUrl} label="Phone Recording" />
    }
    return (
      <div className="py-12 text-center space-y-2">
        <Mic size={32} className="mx-auto text-muted-foreground/40" />
        <p className="text-sm font-medium text-muted-foreground">No recording available</p>
        <p className="text-xs text-muted-foreground/70">
          No Twilio recording was found for this session.
          Ensure call recording is enabled on your Twilio number or trunk.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {recordings.map((recording: RecordingInfo) => (
        <Card key={recording.recording_sid}>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center justify-between">
              <span className="flex items-center gap-2">
                <Mic size={13} className="text-orange-500" /> Phone Recording
              </span>
              <span className="text-xs text-muted-foreground font-normal">
                {formatDuration(recording.duration_sec)}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <audio controls className="w-full" src={`${recording.uri}?token=${API_TOKEN}`}>
              Your browser does not support the audio element.
            </audio>
            <div className="flex items-center justify-between">
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                recording.status === 'completed'
                  ? 'bg-emerald-50 text-emerald-700'
                  : 'bg-amber-50 text-amber-700'
              }`}>
                {recording.status}
              </span>
              <Button variant="outline" size="sm" className="gap-1.5" asChild>
                <a href={`${recording.uri}?token=${API_TOKEN}`} download>
                  <Download size={13} /> Download
                </a>
              </Button>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

function DirectAudioPlayer({ url, label }: { url: string; label: string }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Mic size={13} className="text-orange-500" /> {label}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <audio controls className="w-full" src={url}>
          Your browser does not support the audio element.
        </audio>
        <div className="flex justify-end">
          <Button variant="outline" size="sm" className="gap-1.5" asChild>
            <a href={url} target="_blank" rel="noopener noreferrer" download>
              <Download size={13} /> Download
            </a>
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function formatDuration(seconds: number) {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}m ${s < 10 ? '0' : ''}${s}s`
}

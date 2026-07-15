import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Box, Grid, Typography, alpha, useTheme, Button } from '@mui/material';
import { PageHeader } from '../../../components/PageHeader';
import { PremiumCard } from '../../../components/common/PremiumCard';
import { StatusChip } from '../../../components/common/StatusChip';
import { LoadingCard } from '../../../components/LoadingCard';
import { ErrorState } from '../../../components/feedback/ErrorState';
import { BasicTable } from '../../../components/tables/BasicTable';
import { api, unwrapApiResponse } from '../../../api';
import { useActiveContext } from '../../../contexts/ActiveContext';
import type { components } from '@farmiq/api-client';
import { Camera, Scale, Target, ExternalLink } from 'lucide-react';
import { EmptyState } from '../../../components/EmptyState';

type SessionDetail = components['schemas']['WeighvisionSessionDetailResponse']['data'];
type Prediction = components['schemas']['WeighvisionPrediction'];
type Image = components['schemas']['WeighvisionImage'];
type DetectionRow = {
  id: string;
  capture_id: string;
  detection_index: number;
  selected: boolean;
  class_label: string;
  confidence: number | null;
  area_mm2: number | null;
  width_mm: number | null;
  length_mm: number | null;
  height_mm: number | null;
  depth_mm: number | null;
  pixel_xy: string | null;
  bbox_xyxy: string | null;
};
type SessionDetailView = SessionDetail & {
  session_id?: string;
  initial_weight_kg?: number | null;
  final_weight_kg?: number | null;
  image_count?: number;
  predictions?: Prediction[];
  images?: Image[];
  capture_metadata?: any[];
  detections?: DetectionRow[];
  latest_capture_id?: string | null;
  latest_capture_at?: string | null;
};

function toFiniteNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim().length > 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function toArray<T = unknown>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function toClassLabel(value: unknown): string {
  if (typeof value === 'string' && value.trim().length > 0) {
    return value.trim().toUpperCase();
  }

  if (typeof value === 'number' && Number.isFinite(value)) {
    return value === 0 ? 'CK' : `CLASS_${value}`;
  }

  return 'UNKNOWN';
}

function formatPair(value: unknown): string | null {
  if (!Array.isArray(value) || value.length < 2) return null;
  const x = toFiniteNumber(value[0]);
  const y = toFiniteNumber(value[1]);
  if (x === null || y === null) return null;
  return `${x.toFixed(0)}, ${y.toFixed(0)}`;
}

function formatBbox(value: unknown): string | null {
  if (!Array.isArray(value) || value.length < 4) return null;
  const coords = value
    .slice(0, 4)
    .map((entry) => toFiniteNumber(entry))
    .filter((entry): entry is number => entry !== null);
  if (coords.length < 4) return null;
  return coords.map((entry) => entry.toFixed(0)).join(', ');
}

function normalizeSessionDetail(payload: any): SessionDetailView | null {
  if (!payload || typeof payload !== 'object') return null;

  const measurements = Array.isArray(payload.measurements) ? payload.measurements : [];
  const media = Array.isArray(payload.media) ? payload.media : [];
  const inferences = Array.isArray(payload.inferences) ? payload.inferences : [];
  const captureMetadata = toArray<any>(payload.captureMetadata ?? payload.capture_metadata);

  const finalizedMeasurement =
    measurements.find((entry: any) => entry?.source === 'finalized') ??
    measurements[0];
  const initialMeasurement = measurements[measurements.length - 1] ?? measurements[0];
  const latestCapture = captureMetadata.reduce<any | null>((latest, entry) => {
    if (!entry || typeof entry !== 'object') return latest;
    if (!latest) return entry;

    const latestTs = new Date(
      latest?.occurredAt ?? latest?.occurred_at ?? latest?.createdAt ?? 0
    ).getTime();
    const entryTs = new Date(
      entry?.occurredAt ?? entry?.occurred_at ?? entry?.createdAt ?? 0
    ).getTime();

    return entryTs >= latestTs ? entry : latest;
  }, null);
  const rawMetadata = latestCapture?.rawMetadata ?? latestCapture?.raw_metadata ?? null;
  const detectionEntries = toArray<any>(rawMetadata?.detections);
  const selectedDetectionIndex = toFiniteNumber(
    latestCapture?.selectedDetectionIndex ?? latestCapture?.selected_detection_index
  );
  const detections: DetectionRow[] = detectionEntries.map((entry: any, index) => ({
    id: `${latestCapture?.captureId ?? latestCapture?.capture_id ?? payload?.session_id ?? payload?.sessionId ?? 'capture'}-${index}`,
    capture_id:
      latestCapture?.captureId ??
      latestCapture?.capture_id ??
      rawMetadata?.capture_id ??
      rawMetadata?.image_id ??
      'N/A',
    detection_index: index + 1,
    selected: selectedDetectionIndex !== null && index === selectedDetectionIndex,
    class_label: toClassLabel(entry?.class_name ?? entry?.class_label ?? entry?.class_id),
    confidence: toFiniteNumber(entry?.confidence),
    area_mm2: toFiniteNumber(entry?.area_xy_mm2),
    width_mm: toFiniteNumber(entry?.width_mm),
    length_mm: toFiniteNumber(entry?.length_mm),
    height_mm: toFiniteNumber(entry?.height_mm),
    depth_mm: toFiniteNumber(entry?.depth_mm),
    pixel_xy: formatPair(entry?.pixel_xy),
    bbox_xyxy: formatBbox(entry?.bbox_xyxy),
  }));

  const predictions: Prediction[] = inferences
    .map((entry: any) => {
      const predictedWeightKg = toFiniteNumber(
        entry?.predicted_weight_kg ?? entry?.predictedWeightKg
      );
      if (predictedWeightKg === null) {
        return null;
      }

      return {
        image_id:
          entry?.capture_metadata_id ??
          entry?.captureMetadataId ??
          entry?.media_id ??
          entry?.mediaId ??
          entry?.id,
        timestamp: entry?.ts ?? entry?.timestamp ?? entry?.createdAt,
        predicted_weight_kg: predictedWeightKg,
        confidence_score: toFiniteNumber(
          entry?.confidence ?? entry?.confidence_score ?? entry?.confidenceScore
        ) ?? undefined,
        size_proxy:
          entry?.prediction_mode ??
          entry?.predictionMode ??
          entry?.source_event_type ??
          entry?.sourceEventType,
        is_outlier: false,
      } satisfies Prediction;
    })
    .filter((entry): entry is Prediction => entry !== null);

  const images: Image[] = media.map((entry: any) => ({
    image_id: entry?.objectId ?? entry?.object_id ?? entry?.id,
    presigned_url: undefined,
    expires_at: undefined,
    timestamp: entry?.ts ?? entry?.timestamp ?? entry?.createdAt,
  }));

  return {
    ...(payload as SessionDetailView),
    session_id: payload?.session_id ?? payload?.sessionId ?? payload?.id,
    initial_weight_kg: toFiniteNumber(
      payload?.initial_weight_kg ??
      payload?.initialWeightKg ??
      initialMeasurement?.weightKg ??
      initialMeasurement?.weight_kg
    ),
    final_weight_kg: toFiniteNumber(
      payload?.final_weight_kg ??
      payload?.finalWeightKg ??
      finalizedMeasurement?.weightKg ??
      finalizedMeasurement?.weight_kg
    ),
    image_count:
      (typeof payload?.image_count === 'number' ? payload.image_count : undefined) ??
      (typeof payload?.imageCount === 'number' ? payload.imageCount : undefined) ??
      media.length,
    predictions,
    images,
    capture_metadata: captureMetadata,
    detections,
    latest_capture_id:
      latestCapture?.captureId ??
      latestCapture?.capture_id ??
      rawMetadata?.capture_id ??
      rawMetadata?.image_id ??
      null,
    latest_capture_at:
      latestCapture?.occurredAt ??
      latestCapture?.occurred_at ??
      latestCapture?.createdAt ??
      null,
  };
}

export const SessionDetailPage: React.FC = () => {
  const theme = useTheme();
  const { sessionId } = useParams<{ sessionId: string }>();
  const { tenantId } = useActiveContext();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [session, setSession] = useState<SessionDetailView | null>(null);

  useEffect(() => {
    const fetchSession = async () => {
      if (!tenantId || !sessionId) {
        setLoading(false);
        return;
      }
      setLoading(true);
      try {
        const response = await api.weighvision.session(sessionId, { tenantId });
        const payload = unwrapApiResponse<any>(response);
        setSession(normalizeSessionDetail(payload));
        setError(null);
      } catch (err) {
        setError(err as Error);
      } finally {
        setLoading(false);
      }
    };

    fetchSession();
  }, [tenantId, sessionId]);

  if (loading) {
    return (
      <Box>
        <PageHeader title="Session Details" subtitle="Detailed breakdown of AI inference data and source captures" />
        <LoadingCard title="Loading session details" lines={4} />
      </Box>
    );
  }
  if (error) return <ErrorState title="Failed to load session" message={error.message} />;
  if (!session) {
    return (
      <Box>
        <PageHeader title="Session Details" subtitle="Detailed breakdown of AI inference data and source captures" />
        <EmptyState title="Session not found" description="No session details available for this ID." />
      </Box>
    );
  }

  return (
    <Box sx={{ animation: 'fadeIn 0.6s ease-out' }}>
      <PageHeader
        title={`Session ${session.session_id?.split('-')[0] || 'N/A'}...`}
        subtitle="Detailed breakdown of AI inference data and source captures"
        actions={[
          { label: 'Export Data', variant: 'outlined', startIcon: <ExternalLink size={18} />, onClick: () => {} },
        ]}
      />
      <Grid container spacing={3} mt={1}>
        {[
          {
            label: 'Initial Weight',
            value: typeof session.initial_weight_kg === 'number' ? `${session.initial_weight_kg} kg` : 'N/A',
            icon: <Scale size={24} />,
            color: 'info.main',
          },
          {
            label: 'Final Weight',
            value: typeof session.final_weight_kg === 'number' ? `${session.final_weight_kg} kg` : 'N/A',
            icon: <Target size={24} />,
            color: 'success.main',
          },
          {
            label: 'Inference Captures',
            value: typeof session.image_count === 'number' ? session.image_count : 0,
            icon: <Camera size={24} />,
            color: 'primary.main',
          },
        ].map((stat, idx) => (
          <Grid item xs={12} md={4} key={idx}>
            <PremiumCard>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                <Box
                  sx={{
                    p: 1.5,
                    bgcolor: alpha(
                      stat.color.split('.')[0] === 'primary'
                        ? theme.palette.primary.main
                        : stat.color.split('.')[0] === 'success'
                          ? theme.palette.success.main
                          : theme.palette.info.main,
                      0.1
                    ),
                    color: stat.color,
                    borderRadius: 2,
                  }}
                >
                  {stat.icon}
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary" fontWeight="600" sx={{ textTransform: 'uppercase', letterSpacing: 0.5 }}>
                    {stat.label}
                  </Typography>
                  <Typography variant="h5" fontWeight="800">{stat.value}</Typography>
                </Box>
              </Box>
            </PremiumCard>
          </Grid>
        ))}

        <Grid item xs={12}>
          <PremiumCard title="AI Prediction Stream" noPadding>
            <BasicTable<Prediction>
              columns={[
                {
                  id: 'image_id',
                  label: 'Image ID',
                  format: (v: string) => <Typography variant="caption" sx={{ opacity: 0.7 }}>{v ? `${v.split('-')[0]}...` : 'N/A'}</Typography>,
                },
                {
                  id: 'predicted_weight_kg',
                  label: 'Weight (kg)',
                  align: 'right',
                  format: (v: number) => <strong>{typeof v === 'number' ? v.toFixed(2) : 'N/A'}</strong>,
                },
                {
                  id: 'confidence_score',
                  label: 'Confidence',
                  align: 'right',
                  format: (v: number) => (
                    typeof v === 'number'
                      ? <StatusChip status={v > 0.9 ? 'success' : v > 0.7 ? 'info' : 'warning'} label={`${(v * 100).toFixed(1)}%`} />
                      : 'N/A'
                  ),
                },
                { id: 'size_proxy', label: 'Mode', format: (v: string) => v?.toUpperCase() || 'N/A' },
                {
                  id: 'timestamp',
                  label: 'Timestamp',
                  format: (value: string) => value ? new Date(value).toLocaleString() : 'N/A',
                },
              ]}
              data={session.predictions || []}
              emptyMessage="No predictions available."
              rowKey="image_id"
            />
          </PremiumCard>
        </Grid>

        <Grid item xs={12}>
          <PremiumCard
            title="Individual Detections"
            subtitle={
              session.latest_capture_id
                ? `Latest capture ${session.latest_capture_id}${session.latest_capture_at ? ` at ${new Date(session.latest_capture_at).toLocaleString()}` : ''}`
                : 'Per-object detections from the latest capture metadata'
            }
            noPadding
          >
            <BasicTable<DetectionRow>
              columns={[
                {
                  id: 'detection_index',
                  label: '#',
                  align: 'right',
                },
                {
                  id: 'selected',
                  label: 'Selected',
                  format: (value: boolean) => (
                    <StatusChip
                      status={value ? 'success' : 'info'}
                      label={value ? 'YES' : 'NO'}
                    />
                  ),
                },
                {
                  id: 'class_label',
                  label: 'Class',
                  format: (value: string) => value || 'N/A',
                },
                {
                  id: 'confidence',
                  label: 'Confidence',
                  align: 'right',
                  format: (value: number) =>
                    typeof value === 'number' ? `${(value * 100).toFixed(1)}%` : 'N/A',
                },
                {
                  id: 'area_mm2',
                  label: 'Area (mm²)',
                  align: 'right',
                  format: (value: number) =>
                    typeof value === 'number' ? value.toFixed(2) : 'N/A',
                },
                {
                  id: 'width_mm',
                  label: 'Width (mm)',
                  align: 'right',
                  format: (value: number) =>
                    typeof value === 'number' ? value.toFixed(2) : 'N/A',
                },
                {
                  id: 'length_mm',
                  label: 'Length (mm)',
                  align: 'right',
                  format: (value: number) =>
                    typeof value === 'number' ? value.toFixed(2) : 'N/A',
                },
                {
                  id: 'height_mm',
                  label: 'Height (mm)',
                  align: 'right',
                  format: (value: number) =>
                    typeof value === 'number' ? value.toFixed(2) : 'N/A',
                },
                {
                  id: 'depth_mm',
                  label: 'Depth (mm)',
                  align: 'right',
                  format: (value: number) =>
                    typeof value === 'number' ? value.toFixed(2) : 'N/A',
                },
                {
                  id: 'pixel_xy',
                  label: 'Pixel XY',
                  format: (value: string) => value || 'N/A',
                },
                {
                  id: 'bbox_xyxy',
                  label: 'BBox',
                  format: (value: string) => value || 'N/A',
                },
              ]}
              data={session.detections || []}
              emptyMessage="No per-object detections available for this session."
              rowKey="id"
            />
          </PremiumCard>
        </Grid>

        <Grid item xs={12}>
          <PremiumCard title="Source Image Registry" noPadding>
            <BasicTable<Image>
              columns={[
                {
                  id: 'image_id',
                  label: 'Image ID',
                  format: (v: string) => <Typography variant="caption" sx={{ opacity: 0.7 }}>{v ? `${v.split('-')[0]}...` : 'N/A'}</Typography>,
                },
                {
                  id: 'timestamp',
                  label: 'Captured',
                  format: (value: string) => value ? new Date(value).toLocaleString() : 'N/A',
                },
                {
                  id: 'presigned_url',
                  label: 'Verification',
                  format: (value: string) => value ? <Button size="small" variant="text" startIcon={<ExternalLink size={14} />} href={value} target="_blank" rel="noreferrer">View Original</Button> : 'N/A',
                },
                {
                  id: 'expires_at',
                  label: 'Expiry',
                  format: (value: string) => value ? new Date(value).toLocaleString() : 'N/A',
                },
              ]}
              data={session.images || []}
              emptyMessage="No images available."
              rowKey="image_id"
            />
          </PremiumCard>
        </Grid>
      </Grid>
    </Box>
  );
};

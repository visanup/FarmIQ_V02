import React from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { api, unwrapApiResponse } from '../../../api';
import { Alert, Box, Button, Stack, Typography } from '@mui/material';
import { Camera } from 'lucide-react';
import { PageHeader } from '../../../components/PageHeader';
import { StatusChip } from '../../../components/common/StatusChip';
import { PremiumCard } from '../../../components/common/PremiumCard';
import { BasicTable } from '../../../components/tables/BasicTable';
import { EmptyState } from '../../../components/EmptyState';
import { ErrorState } from '../../../components/feedback/ErrorState';
import { LoadingCard } from '../../../components/LoadingCard';
import { useActiveContext } from '../../../contexts/ActiveContext';
import { useNavigate } from 'react-router-dom';
import type { components } from '@farmiq/api-client';

type Session = components['schemas']['WeighvisionSession'];
type SessionRow = Session & {
    predicted_weight_kg?: number | null;
    prediction_mode?: string | null;
    prediction_confidence?: number | null;
    prediction_batch_id?: string | null;
    prediction_breed_code?: string | null;
    prediction_age_days?: number | null;
    prediction_fallback_engaged?: boolean | null;
    prediction_fallback_reason?: string | null;
};

function toWeighVisionDeviceIdFromStation(stationId: unknown): string | null {
    if (typeof stationId !== 'string' || stationId.trim().length === 0) return null;
    const match = stationId.trim().match(/^st-(\d+)$/i);
    if (!match) return null;
    const seq = Number(match[1]);
    if (!Number.isFinite(seq) || seq < 0) return null;
    return `wv-${String(Math.trunc(seq)).padStart(3, '0')}`;
}

function toFiniteNumber(value: unknown): number | null {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (typeof value === 'string' && value.trim().length > 0) {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : null;
    }
    return null;
}

function getLatestPrediction(item: any) {
    const inferences = Array.isArray(item?.inferences) ? item.inferences : [];
    const prediction =
        inferences.find((entry: any) =>
            toFiniteNumber(entry?.predicted_weight_kg ?? entry?.predictedWeightKg) !== null &&
            (entry?.prediction_mode ?? entry?.predictionMode) === 'shadow'
        ) ??
        inferences.find((entry: any) =>
            toFiniteNumber(entry?.predicted_weight_kg ?? entry?.predictedWeightKg) !== null
        );

    return {
        deviceId: prediction?.device_id ?? prediction?.deviceId ?? null,
        predictedWeightKg: toFiniteNumber(
            prediction?.predicted_weight_kg ?? prediction?.predictedWeightKg
        ),
        predictionMode:
            typeof (prediction?.prediction_mode ?? prediction?.predictionMode) === 'string'
                ? (prediction?.prediction_mode ?? prediction?.predictionMode)
                : null,
        confidence: toFiniteNumber(
            prediction?.confidence ?? prediction?.confidence_score ?? prediction?.confidenceScore
        ),
        batchId: prediction?.batch_id ?? prediction?.batchId ?? null,
        breedCode: prediction?.breed_code ?? prediction?.breedCode ?? null,
        ageDays: toFiniteNumber(prediction?.age_days ?? prediction?.ageDays),
        fallbackEngaged:
            typeof (prediction?.fallback_engaged ?? prediction?.fallbackEngaged) === 'boolean'
                ? (prediction?.fallback_engaged ?? prediction?.fallbackEngaged)
                : null,
        fallbackReason: prediction?.fallback_reason ?? prediction?.fallbackReason ?? null,
    };
}

function normalizeSession(item: any): SessionRow {
    const sessionId = item?.session_id ?? item?.sessionId ?? item?.sessionID ?? item?.id;
    const stationId = item?.station_id ?? item?.stationId;
    const prediction = getLatestPrediction(item);
    const deviceId =
        item?.payload_json?.device_id ??
        item?.payloadJson?.device_id ??
        item?.payload?.device_id ??
        item?.payload?.deviceId ??
        item?.device_id ??
        item?.deviceId ??
        item?.device?.device_id ??
        item?.device?.deviceId ??
        prediction.deviceId ??
        toWeighVisionDeviceIdFromStation(stationId);
    const startAt = item?.start_at ?? item?.startAt ?? item?.ts ?? item?.createdAt;
    const imageCount =
        item?.image_count ??
        item?.imageCount ??
        (Array.isArray(item?.media) ? item.media.length : undefined);
    const latestMeasurementWeight = Array.isArray(item?.measurements) && item.measurements.length > 0
        ? (item.measurements[0]?.weightKg ?? item.measurements[0]?.weight_kg)
        : undefined;
    const finalWeightRaw =
        item?.final_weight_kg ??
        item?.finalWeightKg ??
        item?.weightKg ??
        latestMeasurementWeight;
    const finalWeightKg = toFiniteNumber(finalWeightRaw);

    return {
        ...(item as SessionRow),
        session_id: sessionId as any,
        device_id: deviceId as any,
        start_at: startAt as any,
        image_count: (typeof imageCount === 'number' ? imageCount : 0) as any,
        final_weight_kg: finalWeightKg as any,
        predicted_weight_kg: prediction.predictedWeightKg as any,
        prediction_mode: prediction.predictionMode as any,
        prediction_confidence: prediction.confidence as any,
        prediction_batch_id: prediction.batchId as any,
        prediction_breed_code: prediction.breedCode as any,
        prediction_age_days: prediction.ageDays as any,
        prediction_fallback_engaged: prediction.fallbackEngaged as any,
        prediction_fallback_reason: prediction.fallbackReason as any,
    };
}

const COLUMNS: any[] = [
    {
        id: 'session_id',
        label: 'Session ID',
        format: (v: string) => (
            <Typography variant="caption" fontWeight="600" sx={{ opacity: 0.7 }}>
                {typeof v === 'string' && v.length > 0 ? `${v.split('-')[0]}...` : 'N/A'}
            </Typography>
        ),
    },
    {
        id: 'device_id',
        label: 'Device ID',
        format: (v: string) => (
            <Typography variant="body2" fontWeight="600">
                {typeof v === 'string' && v.length > 0 ? v : 'N/A'}
            </Typography>
        ),
    },
    {
        id: 'stationId',
        label: 'Station',
        format: (_: string, row: SessionRow) => {
            const stationId = (row as any).station_id ?? (row as any).stationId;
            return (
                <Typography variant="body2" fontWeight="600" noWrap>
                    {typeof stationId === 'string' && stationId.length > 0 ? stationId : 'N/A'}
                </Typography>
            );
        },
    },
    {
        id: 'batchId',
        label: 'Batch Context',
        format: (_: string, row: SessionRow) => {
            const batchId = row.prediction_batch_id ?? (row as any).batchId ?? (row as any).batch_id;
            const breed = row.prediction_breed_code;
            const ageDays = row.prediction_age_days;
            if (!batchId) {
                return (
                    <Box>
                        <Typography variant="caption" color="warning.main" fontWeight="700">
                            UNASSIGNED
                        </Typography>
                        <Typography variant="caption" display="block" color="text.secondary">
                            Bind this station in Batches &amp; Flocks
                        </Typography>
                    </Box>
                );
            }
            return (
                <Box>
                    <Typography variant="body2" fontWeight="600">{batchId}</Typography>
                    <Typography variant="caption" color="text.secondary">
                        {breed || 'Breed unavailable'}{ageDays !== null && ageDays !== undefined ? ` · day ${ageDays}` : ''}
                    </Typography>
                </Box>
            );
        },
    },
    {
        id: 'start_at',
        label: 'Start Time',
        format: (v: string) => (v ? new Date(v).toLocaleString() : 'N/A'),
    },
    {
        id: 'image_count',
        label: 'Images',
        align: 'right',
        format: (v: number) => (
            <Typography variant="body2" fontWeight="700" color="primary">
                {Number.isFinite(v) ? v : 0}
            </Typography>
        ),
    },
    {
        id: 'predicted_weight_kg',
        label: 'Predicted Weight',
        align: 'right',
        format: (_: number, row: SessionRow) => {
            const predictedWeight = toFiniteNumber(row?.predicted_weight_kg);
            const confidence = toFiniteNumber(row?.prediction_confidence);
            const predictionMode = typeof row?.prediction_mode === 'string' ? row.prediction_mode : null;

            if (predictedWeight === null) {
                return 'N/A';
            }

            return (
                <Box sx={{ textAlign: 'right' }}>
                    <Typography variant="body2" fontWeight="700" color="secondary.main">
                        {`${predictedWeight.toFixed(2)} kg`}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                        {predictionMode ? predictionMode.toUpperCase() : 'PRED'}
                        {confidence !== null ? ` | ${(confidence * 100).toFixed(0)}%` : ''}
                    </Typography>
                </Box>
            );
        },
    },
    {
        id: 'final_weight_kg',
        label: 'Final Weight',
        align: 'right',
        format: (v: number) => (
            <strong>{typeof v === 'number' ? `${v.toFixed(2)} kg` : 'N/A'}</strong>
        ),
    },
    {
        id: 'prediction_fallback_engaged',
        label: 'Model Status',
        format: (_: boolean, row: SessionRow) => {
            if (row.prediction_fallback_engaged) {
                return <StatusChip status="warning" label={row.prediction_fallback_reason || 'FALLBACK'} />;
            }
            return <StatusChip status="success" label="POLICY MATCH" />;
        },
    },
    {
        id: 'status',
        label: 'Status',
        format: (v: string) => (
            <StatusChip
                status={v === 'completed' ? 'success' : v === 'active' ? 'info' : 'info'}
                label={typeof v === 'string' && v.length > 0 ? v.toUpperCase() : 'UNKNOWN'}
            />
        ),
    },
];

export const SessionsListPage: React.FC = () => {
    const { tenantId, farmId, barnId, batchId, timeRange } = useActiveContext();
    const navigate = useNavigate();
    const historicalPayload = {
        tenantId,
        farmId,
        barnId,
        batchId,
        from: timeRange.start.toISOString(),
        to: timeRange.end.toISOString(),
        reason: 'Late Batch registration: user-confirmed historical association',
    };
    const historicalReady = Boolean(tenantId && farmId && barnId && batchId);
    const historicalPreview = useMutation({
        mutationFn: () => api.weighvision.historicalAssociationPreview(historicalPayload),
    });
    const historicalConfirm = useMutation({
        mutationFn: () => api.weighvision.historicalAssociationConfirm(historicalPayload),
    });
    const historicalReprocess = useMutation({
        mutationFn: () => api.weighvision.historicalReprocess(historicalPayload),
    });
    const { data: sessions = [], isLoading: loading, error } = useQuery<SessionRow[]>({
        queryKey: ['sessions', tenantId, farmId, barnId, batchId, timeRange.start, timeRange.end],
        queryFn: async () => {
            if (!tenantId) return [];
            const from = timeRange.start.toISOString();
            const to = timeRange.end.toISOString();

            const response = await api.weighvision.sessions({
                tenantId,
                farmId: farmId || undefined,
                barnId: barnId || undefined,
                batchId: batchId || undefined,
                from,
                to,
                limit: 100,
            });

            const data = unwrapApiResponse<any>(response);
            if (data?.items && Array.isArray(data.items)) {
                return data.items.map(normalizeSession);
            }
            if (Array.isArray(data)) {
                return data.map(normalizeSession);
            }
            return [];
        },
        enabled: !!tenantId,
        initialData: [],
    });

    if (error) {
        return <ErrorState title="Failed to load sessions" message={error.message} />;
    }

    if (loading) {
        return (
            <Box>
                <PageHeader title="WeighVision Sessions" subtitle="Historical log of AI-powered weighing sessions and inference capture results" />
                <LoadingCard title="Loading sessions" lines={3} />
            </Box>
        );
    }

    if (!loading && sessions.length === 0) {
        return (
            <Box sx={{ animation: 'fadeIn 0.6s ease-out' }}>
                <PageHeader title="WeighVision Sessions" />
                <PremiumCard>
                    <EmptyState
                        icon={<Camera size={32} />}
                        title="No Sessions Found"
                        description="No scanning sessions are currently active for the selected context."
                        size="sm"
                    />
                </PremiumCard>
            </Box>
        );
    }

    return (
        <Box sx={{ animation: 'fadeIn 0.6s ease-out' }}>
            <PageHeader
                title="WeighVision Sessions"
                subtitle="Historical log of AI-powered weighing sessions and inference capture results"
            />
            <PremiumCard sx={{ mb: 2 }}>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ md: 'center' }}>
                    <Box sx={{ flex: 1 }}>
                        <Typography variant="subtitle2">Historical Batch Association</Typography>
                        <Typography variant="body2" color="text.secondary">
                            Preview first; confirmation only associates unassigned sessions. Reprocess is optional and runs in the isolated historical queue.
                        </Typography>
                    </Box>
                    <Button variant="outlined" disabled={!historicalReady || historicalPreview.isPending}
                        onClick={() => historicalPreview.mutate()}>Preview</Button>
                    <Button variant="contained" color="warning" disabled={!historicalReady || historicalConfirm.isPending}
                        onClick={() => historicalConfirm.mutate()}>Confirm association</Button>
                    <Button variant="outlined" disabled={!historicalReady || historicalReprocess.isPending}
                        onClick={() => historicalReprocess.mutate()}>Queue reprocess</Button>
                </Stack>
                {!historicalReady && <Alert severity="info" sx={{ mt: 1.5 }}>Select tenant, farm, barn, and Batch before historical actions.</Alert>}
                {historicalPreview.data && <Alert severity="info" sx={{ mt: 1.5 }}>Preview ready: {JSON.stringify(unwrapApiResponse<any>(historicalPreview.data))}</Alert>}
                {historicalConfirm.data && <Alert severity="success" sx={{ mt: 1.5 }}>Association confirmed: {JSON.stringify(unwrapApiResponse<any>(historicalConfirm.data))}</Alert>}
                {historicalReprocess.data && <Alert severity="success" sx={{ mt: 1.5 }}>Historical job queued: {JSON.stringify(unwrapApiResponse<any>(historicalReprocess.data))}</Alert>}
                {(historicalPreview.error || historicalConfirm.error || historicalReprocess.error) && <Alert severity="error" sx={{ mt: 1.5 }}>Historical action failed. Check Batch interval, scope, and retained media.</Alert>}
            </PremiumCard>
            <PremiumCard noPadding>
                <BasicTable
                    columns={COLUMNS}
                    data={sessions}
                    loading={loading}
                    rowKey="session_id"
                    onRowClick={(row) => navigate(`/weighvision/sessions/${row.session_id}`)}
                />
            </PremiumCard>
        </Box>
    );
};

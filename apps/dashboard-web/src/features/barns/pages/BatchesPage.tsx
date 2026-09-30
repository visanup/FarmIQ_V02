import React, { useEffect, useMemo, useState } from 'react';
import { Box, Typography, Dialog, DialogTitle, DialogContent, DialogActions, TextField, Button, MenuItem } from '@mui/material';
import { useParams } from 'react-router-dom';
import { PageHeader } from '../../../components/PageHeader';
import { PremiumCard } from '../../../components/common/PremiumCard';
import { BasicTable } from '../../../components/tables/BasicTable';
import { EmptyState } from '../../../components/EmptyState';
import { ErrorState } from '../../../components/feedback/ErrorState';
import { LoadingCard } from '../../../components/LoadingCard';
import { useBatches, Batch } from '../../../hooks/useBatches';
import { useActiveContext } from '../../../contexts/ActiveContext';
import { api } from '../../../api';
import { ClipboardList } from 'lucide-react';
import { z } from 'zod';

const SPECIES_OPTIONS = ['broiler', 'layer', 'swine', 'fish'];
const SEX_OPTIONS = [
  { value: 'as_hatched', label: 'As-Hatched' },
  { value: 'male', label: 'Male' },
  { value: 'female', label: 'Female' },
];
// Dev model catalog.  A production implementation should fetch this catalog
// from the Cloud ML model registry for the selected tenant/site.
const BREED_MODEL_CATALOG: Record<string, { sexes: string[]; availability: 'approved' | 'fallback' }> = {
  'Arbor Acres Plus': { sexes: ['as_hatched', 'male', 'female'], availability: 'approved' },
  'Ross 308': { sexes: ['male', 'female'], availability: 'fallback' },
};
const BATCH_STATUS_OPTIONS = [
  { value: 'active', label: 'Active — รอบที่ Edge ใช้งานอยู่' },
  { value: 'completed', label: 'Completed — ปิดรอบและเก็บประวัติ' },
  { value: 'cancelled', label: 'Cancelled — ยกเลิกรอบ' },
];

export const BatchesPage: React.FC = () => {
  const { barnId: routeBarnId } = useParams<{ barnId: string }>();
  const { tenantId, farmId, barnId } = useActiveContext();
  const effectiveBarnId = routeBarnId || barnId || undefined;
  const { data: batches, isLoading, error, refetch } = useBatches({ farmId: farmId || undefined, barnId: effectiveBarnId });
  const [createOpen, setCreateOpen] = useState(false);
  const [species, setSpecies] = useState('broiler');
  const [breed, setBreed] = useState('Arbor Acres Plus');
  const [sex, setSex] = useState('as_hatched');
  const [headcount, setHeadcount] = useState('');
  const [status, setStatus] = useState('active');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [createError, setCreateError] = useState<string | null>(null);
  const [editingBatch, setEditingBatch] = useState<any | null>(null);
  const [deletingBatch, setDeletingBatch] = useState<any | null>(null);
  const [bindingBatch, setBindingBatch] = useState<any | null>(null);
  const [bindingDeviceId, setBindingDeviceId] = useState('');
  const [bindingStationId, setBindingStationId] = useState('');
  const [bindingStatus, setBindingStatus] = useState<string | null>(null);
  const [bindingConflict, setBindingConflict] = useState<{ batchId: string } | null>(null);
  const [bindingDevices, setBindingDevices] = useState<any[]>([]);
  const allowedSexes = BREED_MODEL_CATALOG[breed]?.sexes || [];
  const availableSexOptions = SEX_OPTIONS.filter((option) => allowedSexes.includes(option.value));

  const createSchema = z.object({
    species: z.string().min(1, 'Species is required'),
    status: z.enum(['active', 'completed', 'cancelled']),
    breed: z.string().min(1, 'Breed is required'),
    sex: z.enum(['as_hatched', 'male', 'female']),
    headcount: z.number().int().positive().optional(),
    startDate: z.string().optional(),
    endDate: z.string().optional(),
  });

  const createDisabled = useMemo(
    () => !tenantId || !farmId || !effectiveBarnId || !species.trim() || !breed.trim() || !sex,
    [tenantId, farmId, effectiveBarnId, species, breed, sex]
  );

  useEffect(() => {
    if (!bindingBatch || !tenantId || !farmId || !effectiveBarnId) return;
    void api.devices.list({ tenantId, farmId, barnId: effectiveBarnId, page: 1, pageSize: 100 })
      .then((response) => setBindingDevices((response.data as any)?.data || response.data || []))
      .catch(() => setBindingDevices([]));
  }, [bindingBatch, tenantId, farmId, effectiveBarnId]);

  const handleCreate = async () => {
    if (!tenantId || !farmId || !effectiveBarnId || !species.trim()) return;
    try {
      const parsed = createSchema.safeParse({
        species: species.trim(),
        status: status || 'active',
        breed: breed.trim() || undefined,
        sex,
        headcount: headcount ? Number(headcount) : undefined,
        startDate: startDate || undefined,
        endDate: endDate || undefined,
      });
      if (!parsed.success) {
        setCreateError(parsed.error.issues[0]?.message || 'Invalid batch details');
        return;
      }
      await api.batches.create({
        farmId,
        barnId: effectiveBarnId,
        species: parsed.data.species,
        breedCode: parsed.data.breed,
        sex: parsed.data.sex,
        initialHeadcount: parsed.data.headcount,
        status: parsed.data.status,
        startDate: parsed.data.startDate,
        endDate: parsed.data.endDate,
      });
      setCreateOpen(false);
      setStartDate('');
      setEndDate('');
      setBreed('Arbor Acres Plus');
      setSex('as_hatched');
      setHeadcount('');
      setCreateError(null);
      await refetch();
    } catch (err: any) {
      setCreateError(err?.message || 'Failed to create batch');
    }
  };

  const handleUpdate = async () => {
    if (!editingBatch) return;
    try {
      await api.batches.update(editingBatch.id, {
        tenantId,
        species,
        status,
        breedCode: breed.trim(),
        sex,
        initialHeadcount: headcount ? Number(headcount) : undefined,
        startDate: startDate ? new Date(startDate).toISOString() : undefined,
        endDate: endDate ? new Date(endDate).toISOString() : undefined,
      });
      setEditingBatch(null); setCreateError(null); await refetch();
    } catch (err: any) { setCreateError(err?.message || 'Failed to update batch'); }
  };

  const openEdit = (batch: any) => {
    setEditingBatch(batch); setSpecies(batch.species || 'broiler'); setBreed(batch.breedCode || 'Arbor Acres Plus');
    setSex(batch.sex || 'as_hatched');
    setHeadcount(batch.initialHeadcount?.toString() || ''); setStatus(batch.status || 'active');
    setStartDate(batch.startDate ? new Date(batch.startDate).toISOString().slice(0, 16) : '');
    setEndDate(batch.endDate ? new Date(batch.endDate).toISOString().slice(0, 16) : ''); setCreateError(null);
  };

  const handleDelete = async () => {
    if (!deletingBatch || !tenantId) return;
    try {
      await api.batches.delete(deletingBatch.id, { tenantId });
      await refetch();
    } catch (err: any) {
      setCreateError(err?.message || 'Failed to delete batch');
    } finally {
      setDeletingBatch(null);
    }
  };

  const handleCreateBinding = async () => {
    if (!bindingBatch || !bindingDeviceId.trim()) return;
    const deviceId = bindingDeviceId.trim();
    const stationId = bindingStationId.trim();
    const conflictingBatch = batches.find((batch: any) =>
      batch.id !== bindingBatch.id &&
      batch.status === 'active' &&
      batch.devices?.some((device: any) =>
        device.id === deviceId &&
        (!stationId || device.metadata?.stationId === stationId)
      )
    );
    if (conflictingBatch) {
      setBindingConflict({ batchId: conflictingBatch.id });
      return;
    }
    try {
      const response = await api.batches.bindings.create(bindingBatch.id, {
        tenantId: tenantId || undefined,
        deviceId: bindingDeviceId.trim(),
        stationId: bindingStationId.trim() || undefined,
      });
      const result = response.data?.data ?? response.data;
      setBindingStatus(`Binding saved. Edge context revision ${result?.revision ?? 'pending'} will sync on the next Edge refresh.`);
      setBindingDeviceId('');
      setBindingStationId('');
      await refetch();
    } catch (err: any) {
      if (err?.response?.status === 422) {
        const available = bindingDevices.map((device) => {
          const deviceName = device.serialNo || device.id;
          const stationName = device?.metadata?.stationId || 'ยังไม่มี Station ผูกไว้';
          return `Device: ${deviceName} | Station: ${stationName}`;
        });
        setBindingStatus([
          'ไม่สามารถผูก Batch ได้: Device หรือ Station ที่เลือกไม่ได้อยู่ใน Farm/Barn เดียวกับ Batch นี้',
          available.length
            ? `รายการที่ใช้ได้ใน Barn นี้: ${available.join(' ; ')}`
            : 'Barn นี้ยังไม่มี Device หรือ Station ที่ลงทะเบียนไว้',
          'กรุณาเลือกจากรายการด้านบน แล้วลองบันทึกอีกครั้ง',
        ].join('\n'));
      } else {
        setBindingStatus(err?.message || 'ไม่สามารถสร้างการผูก Batch ได้ โปรดลองอีกครั้ง');
      }
    }
  };

  if (isLoading) {
    return (
      <Box>
        <PageHeader title="Batches & Flocks" subtitle="Track active cohorts within barns" />
        <LoadingCard title="Loading batches" lines={3} />
      </Box>
    );
  }

  if (error) return <ErrorState title="Failed to load batches" message={error.message} />;

  return (
    <Box sx={{ animation: 'fadeIn 0.6s ease-out' }}>
      <PageHeader
        title="Batches & Flocks"
        subtitle="Track active cohorts within barns"
        actions={[
          {
            label: 'Create Batch',
            variant: 'contained',
            startIcon: <ClipboardList size={18} />,
            onClick: () => setCreateOpen(true),
          },
        ]}
      />

      {batches.length === 0 ? (
        <EmptyState
          icon={<ClipboardList size={32} />}
          title="No batches found"
          description="Create a batch to start tracking flock performance."
        />
      ) : (
        <PremiumCard noPadding>
          <BasicTable<Batch>
            columns={[
              { id: 'actions', label: 'Actions', format: (_value, row: any) => <Box sx={{ display: 'flex', gap: 1 }}><Button size="small" onClick={(event) => { event.stopPropagation(); openEdit(row); }}>Edit</Button><Button size="small" onClick={(event) => { event.stopPropagation(); setBindingBatch(row); setBindingStatus(null); }}>Bind station</Button><Button size="small" color="error" onClick={(event) => { event.stopPropagation(); setDeletingBatch(row); }}>Delete</Button></Box> },
              { id: 'batch_id', label: 'Batch ID' },
              { id: 'species', label: 'Species' },
              { id: 'breedCode', label: 'Breed' },
              { id: 'sex', label: 'Sex', format: (value) => SEX_OPTIONS.find((option) => option.value === value)?.label || '—' },
              { id: 'initialHeadcount', label: 'Initial Headcount' },
              { id: 'status', label: 'Status' },
              {
                id: 'start_date',
                label: 'Start Date',
                format: (value) => (value ? new Date(value).toLocaleDateString() : '—'),
              },
              {
                id: 'end_date',
                label: 'End Date',
                format: (value) => (value ? new Date(value).toLocaleDateString() : '—'),
              },
            ]}
            data={batches.map((batch) => ({
              ...batch,
              batch_id: batch.batch_id || batch.id,
              start_date: batch.start_date || (batch as any).startDate,
              end_date: batch.end_date || (batch as any).endDate,
              breedCode: (batch as any).breed_code || (batch as any).breedCode || '—',
              sex: (batch as any).sex || '—',
              initialHeadcount: (batch as any).initial_headcount ?? (batch as any).initialHeadcount ?? '—',
            }))}
            rowKey="batch_id"
          />
        </PremiumCard>
      )}

      <Dialog open={createOpen || !!editingBatch} onClose={() => { setCreateOpen(false); setEditingBatch(null); }} maxWidth="sm" fullWidth>
        <DialogTitle>{editingBatch ? 'Edit Batch' : 'Create Batch'}</DialogTitle>
        <DialogContent sx={{ display: 'grid', gap: 2, pt: 1 }}>
          <TextField
            select
            label="Species"
            value={species}
            onChange={(event) => setSpecies(event.target.value)}
            fullWidth
          >
            {SPECIES_OPTIONS.map((option) => (
              <MenuItem key={option} value={option}>
                {option}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            select
            label="Status"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
            helperText="Only an active batch can be resolved by Edge."
            fullWidth
          >
            {BATCH_STATUS_OPTIONS.map((option) => (
              <MenuItem key={option.value} value={option.value}>{option.label}</MenuItem>
            ))}
          </TextField>
          <TextField
            select
            label="Breed"
            value={breed}
            onChange={(event) => {
              const nextBreed = event.target.value;
              setBreed(nextBreed);
              const allowed = BREED_MODEL_CATALOG[nextBreed]?.sexes || [];
              if (!allowed.includes(sex)) setSex(allowed[0] || '');
            }}
            fullWidth
            helperText="Maps to the approved XGBoost broiler model"
          >
            {Object.entries(BREED_MODEL_CATALOG).map(([breedCode, model]) => (
              <MenuItem key={breedCode} value={breedCode}>{breedCode}{model.availability === 'fallback' ? ' (Dev fallback)' : ''}</MenuItem>
            ))}
          </TextField>
          <TextField
            select
            label="Sex"
            value={sex}
            onChange={(event) => setSex(event.target.value)}
            helperText={BREED_MODEL_CATALOG[breed]?.availability === 'fallback' ? 'Ross 308 is currently available in Dev fallback mode.' : 'Required XGBoost growth-standard context'}
            fullWidth
          >
            {availableSexOptions.map((option) => (
              <MenuItem key={option.value} value={option.value}>{option.label}</MenuItem>
            ))}
          </TextField>
          <TextField
            label="Headcount"
            type="number"
            value={headcount}
            onChange={(event) => setHeadcount(event.target.value)}
            fullWidth
          />
          <TextField
            label="Start date"
            type="datetime-local"
            value={startDate}
            onChange={(event) => setStartDate(event.target.value)}
            InputLabelProps={{ shrink: true }}
            fullWidth
          />
          <TextField
            label="End date"
            type="datetime-local"
            value={endDate}
            onChange={(event) => setEndDate(event.target.value)}
            InputLabelProps={{ shrink: true }}
            fullWidth
          />
          {!farmId || !effectiveBarnId ? (
            <Typography variant="body2" color="warning.main">
              Select a farm and barn before creating a batch.
            </Typography>
          ) : null}
          {createError ? (
            <Typography variant="body2" color="error">
              {createError}
            </Typography>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => { setCreateOpen(false); setEditingBatch(null); }}>Cancel</Button>
          <Button variant="contained" disabled={editingBatch ? !breed.trim() : createDisabled} onClick={editingBatch ? handleUpdate : handleCreate}>
            {editingBatch ? 'Save changes' : 'Create Batch'}
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={!!deletingBatch} onClose={() => setDeletingBatch(null)}>
        <DialogTitle>Delete batch?</DialogTitle>
        <DialogContent><Typography>This permanently deletes this Batch from the Dev database.</Typography></DialogContent>
        <DialogActions><Button onClick={() => setDeletingBatch(null)}>Cancel</Button><Button color="error" variant="contained" onClick={handleDelete}>Delete</Button></DialogActions>
      </Dialog>
      <Dialog open={!!bindingBatch} onClose={() => setBindingBatch(null)} maxWidth="sm" fullWidth>
        <DialogTitle>Bind station to Batch {bindingBatch?.batch_id || bindingBatch?.id}</DialogTitle>
        <DialogContent sx={{ display: 'grid', gap: 2, pt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            The selected device and optional station must belong to this Batch's farm and barn. Saving creates a new Edge context revision.
          </Typography>
          <TextField select label="Device" value={bindingDeviceId} onChange={(event) => {
            const device = bindingDevices.find((item) => item.id === event.target.value);
            setBindingDeviceId(event.target.value);
            setBindingStationId(device?.metadata?.stationId || '');
          }} required fullWidth>
            {bindingDevices.map((device) => <MenuItem key={device.id} value={device.id}>{device.serialNo || device.id}</MenuItem>)}
          </TextField>
          <TextField select label="Station" value={bindingStationId} onChange={(event) => setBindingStationId(event.target.value)} fullWidth>
            {[...new Set(bindingDevices.map((device) => device?.metadata?.stationId).filter(Boolean))].map((stationId) => <MenuItem key={stationId} value={stationId}>{stationId}</MenuItem>)}
          </TextField>
          {bindingStatus && <Typography variant="body2" color={bindingStatus.startsWith('Binding saved') ? 'success.main' : 'error'} sx={{ whiteSpace: 'pre-line' }}>{bindingStatus}</Typography>}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setBindingBatch(null)}>Close</Button>
          <Button variant="contained" disabled={!bindingDeviceId.trim()} onClick={handleCreateBinding}>Save binding</Button>
        </DialogActions>
      </Dialog>
      <Dialog open={!!bindingConflict} onClose={() => setBindingConflict(null)}>
        <DialogTitle>Active Batch already bound</DialogTitle>
        <DialogContent>
          <Typography>
            This tenant, device, and station already have active Batch {bindingConflict?.batchId}.
            Complete or cancel that Batch before binding this station to another active Batch.
          </Typography>
        </DialogContent>
        <DialogActions><Button variant="contained" onClick={() => setBindingConflict(null)}>Understood</Button></DialogActions>
      </Dialog>
    </Box>
  );
};

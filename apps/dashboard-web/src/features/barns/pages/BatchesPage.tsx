import React, { useMemo, useState } from 'react';
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
// These values are canonical ML metadata.  The current approved XGBoost package
// supports the Arbor Acres Plus broiler standard only.
const BREED_OPTIONS = ['Arbor Acres Plus'];
const SEX_OPTIONS = [
  { value: 'as_hatched', label: 'As-Hatched' },
  { value: 'male', label: 'Male' },
  { value: 'female', label: 'Female' },
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

  const createSchema = z.object({
    species: z.string().min(1, 'Species is required'),
    status: z.string().min(1, 'Status is required'),
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
        farm_id: farmId,
        barn_id: effectiveBarnId,
        species: parsed.data.species,
        breedCode: parsed.data.breed,
        sex: parsed.data.sex,
        initialHeadcount: parsed.data.headcount,
        status: parsed.data.status,
        start_date: parsed.data.startDate,
        end_date: parsed.data.endDate,
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
      setBindingStatus(err?.message || 'Failed to create batch binding');
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
            label="Status"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
            helperText="active, completed, or cancelled"
            fullWidth
          />
          <TextField
            select
            label="Breed"
            value={breed}
            onChange={(event) => setBreed(event.target.value)}
            fullWidth
            helperText="Maps to the approved XGBoost broiler model"
          >
            {BREED_OPTIONS.map((option) => (
              <MenuItem key={option} value={option}>{option}</MenuItem>
            ))}
          </TextField>
          <TextField
            select
            label="Sex"
            value={sex}
            onChange={(event) => setSex(event.target.value)}
            helperText="Required XGBoost growth-standard context"
            fullWidth
          >
            {SEX_OPTIONS.map((option) => (
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
          <TextField label="Device ID" value={bindingDeviceId} onChange={(event) => setBindingDeviceId(event.target.value)} required fullWidth />
          <TextField label="Station ID (optional)" value={bindingStationId} onChange={(event) => setBindingStationId(event.target.value)} fullWidth />
          {bindingStatus && <Typography variant="body2" color={bindingStatus.startsWith('Binding saved') ? 'success.main' : 'error'}>{bindingStatus}</Typography>}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setBindingBatch(null)}>Close</Button>
          <Button variant="contained" disabled={!bindingDeviceId.trim()} onClick={handleCreateBinding}>Save binding</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

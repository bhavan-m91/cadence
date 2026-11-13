import { useMemo } from 'react'
import { flattenCategories, useCategories, useTags } from '@/api/hooks/useTaxonomy'
import { useProjects, useTasks } from '@/api/hooks/useTasks'
import { Select } from '../ui/Field'
import { TagChip } from './Chips'

interface CategorySelectProps {
  value: string
  onChange: (id: string) => void
  id?: string
  describedBy?: string
  includeArchived?: boolean
  exclude?: string[]
  placeholder?: string
  dense?: boolean
}

export function CategorySelect({ value, onChange, id, describedBy, exclude = [], placeholder, dense, includeArchived }: CategorySelectProps) {
  const { data } = useCategories()
  const grouped = useMemo(() => (data ?? []).map((root) => ({ root, items: flattenCategories(root.children, includeArchived).filter((c) => !exclude.includes(c.id)) })), [data, exclude, includeArchived])
  return (
    <Select id={id} aria-describedby={describedBy} value={value} dense={dense} onChange={(e) => onChange(e.target.value)}>
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {grouped.map(({ root, items }) => (
        <optgroup key={root.id} label={root.name}>
          {!exclude.includes(root.id) && <option value={root.id}>{root.name} (general)</option>}
          {items.map((c) => <option key={c.id} value={c.id}>{'  '.repeat(Math.max(0, c.depth - 2))}{c.label.replace(`${root.name} › `, '')}</option>)}
        </optgroup>
      ))}
    </Select>
  )
}

export function TagPicker({ value, onChange }: { value: string[]; onChange: (ids: string[]) => void }) {
  const { data: tags = [] } = useTags()
  const byId = new Map(tags.map((t) => [t.id, t]))
  const available = tags.filter((t) => !value.includes(t.id))
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-1.5">
        {value.length === 0 && <span className="text-xs text-faint">No tags</span>}
        {value.map((id) => {
          const t = byId.get(id)
          return t ? <TagChip key={id} name={t.name} color={t.color} onRemove={() => onChange(value.filter((x) => x !== id))} /> : null
        })}
      </div>
      {available.length > 0 && (
        <Select dense aria-label="Add a tag" value="" onChange={(e) => e.target.value && onChange([...value, e.target.value])}>
          <option value="">Add a tag…</option>
          {available.map((t) => <option key={t.id} value={t.id}>#{t.name}</option>)}
        </Select>
      )}
    </div>
  )
}

export function TaskSelect({ value, onChange, id }: { value: string; onChange: (id: string) => void; id?: string }) {
  const { data = [] } = useTasks({ status: 'open' })
  return (
    <Select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">No task</option>
      {data.map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}
    </Select>
  )
}

export function ProjectSelect({ value, onChange, id, dense }: { value: string; onChange: (id: string) => void; id?: string; dense?: boolean }) {
  const { data = [] } = useProjects()
  return (
    <Select id={id} value={value} dense={dense} onChange={(e) => onChange(e.target.value)}>
      <option value="">No project</option>
      {data.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
    </Select>
  )
}

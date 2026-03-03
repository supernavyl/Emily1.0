interface Device {
  index: number
  name: string
}

interface Props {
  label: string
  devices: Device[]
  selected: number | null
  onChange: (index: number) => void
}

export function DeviceSelector({ label, devices, selected, onChange }: Props) {
  return (
    <div>
      <label className="text-xs text-text-secondary mb-1 block">{label}</label>
      <select
        value={selected ?? ''}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full bg-surface border border-border rounded-lg px-3 py-1.5 text-sm text-text-primary"
      >
        {devices.map(d => (
          <option key={d.index} value={d.index}>
            {d.name} {d.index === selected ? '●' : ''}
          </option>
        ))}
      </select>
    </div>
  )
}

<script lang="ts">
  /**
   * The GIS rule for a "from my data" field: which column, and how its values become
   * the field's options (numeric ranges or a value mapping). Emits the whole updated
   * field; the parent writes it to the store and refreshes its preview.
   */
  import type { GISColumn, SemanticField } from '../../types/semanticFields';
  import { ensureTransformationRule, initCategoricalGroups, initNumericRanges } from '../../utils/semanticFieldRules';
  import Explain from '../Explain.svelte';
  import Select from '../Select.svelte';
  import { HELP } from '../../help';
  const help = HELP.semanticFields;

  let {
    field,
    gisColumns,
    onChange,
  }: {
    field: SemanticField;
    gisColumns: GISColumn[];
    onChange: (next: SemanticField) => void;
  } = $props();

  function setSourceColumn(sourceColumn: string) {
    let next = ensureTransformationRule(
      {
        ...field,
        transformationRule: {
          ...(field.transformationRule || {
            id: crypto.randomUUID(),
            type: field.dataType === 'numeric' ? 'numeric_range' : 'categorical_mapping',
            sourceColumn,
            targetField: field.name,
          }),
          sourceColumn,
          targetField: field.name,
        },
      },
      gisColumns
    );
    if (next.transformationRule?.type === 'categorical_mapping') {
      next = {
        ...next,
        transformationRule: {
          ...next.transformationRule,
          categoricalGroups: initCategoricalGroups(sourceColumn, next.options, gisColumns),
        },
      };
    }
    onChange(next);
  }

  function setRuleType(type: 'numeric_range' | 'categorical_mapping') {
    const sourceColumn = field.transformationRule?.sourceColumn;
    const next: SemanticField = {
      ...field,
      dataType: type === 'numeric_range' ? 'numeric' : 'categorical',
      transformationRule: {
        ...(field.transformationRule || { id: crypto.randomUUID(), sourceColumn: '', targetField: field.name }),
        type,
        numericRanges: type === 'numeric_range' ? initNumericRanges(field.options) : undefined,
        categoricalGroups:
          type === 'categorical_mapping' && sourceColumn
            ? initCategoricalGroups(sourceColumn, field.options, gisColumns)
            : undefined,
      },
    };
    onChange(ensureTransformationRule(next, gisColumns));
  }

  function setRange(index: number, key: 'min' | 'max' | 'label', value: string) {
    const rule = field.transformationRule;
    if (!rule?.numericRanges) return;
    const numericRanges = rule.numericRanges.map((range, i) =>
      i === index ? { ...range, [key]: key === 'label' ? value : Number(value) } : range
    );
    onChange({ ...field, transformationRule: { ...rule, numericRanges } });
  }

  function setGroup(index: number, groupLabel: string) {
    const rule = field.transformationRule;
    if (!rule?.categoricalGroups) return;
    const categoricalGroups = rule.categoricalGroups.map((group, i) =>
      i === index ? { ...group, groupLabel } : group
    );
    onChange({ ...field, transformationRule: { ...rule, categoricalGroups } });
  }
</script>

<div class="field-grid">
  <label>
    GIS column
    <Select
      value={field.transformationRule?.sourceColumn || ''}
      options={gisColumns.map((column) => ({ value: column.name, label: column.name }))}
      placeholder="Select column"
      onChange={setSourceColumn}
    />
  </label>
  <label>
    Rule type
    <Select
      value={field.transformationRule?.type || 'categorical_mapping'}
      options={[
        { value: 'numeric_range', label: 'Numeric ranges' },
        { value: 'categorical_mapping', label: 'Categorical mapping' },
      ]}
      onChange={(value) => setRuleType(value as 'numeric_range' | 'categorical_mapping')}
    />
  </label>
</div>

{#if field.transformationRule?.type === 'numeric_range'}
  <h3>Ranges <Explain text={help.ranges} tip /></h3>
  <Explain text={help.ranges} />
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Option</th>
          <th>Min</th>
          <th>Max</th>
        </tr>
      </thead>
      <tbody>
        {#each field.transformationRule.numericRanges || [] as range, index}
          <tr>
            <td>
              <input
                value={range.label}
                oninput={(event) => setRange(index, 'label', (event.currentTarget as HTMLInputElement).value)}
              />
            </td>
            <td>
              <input
                type="number"
                value={range.min}
                oninput={(event) => setRange(index, 'min', (event.currentTarget as HTMLInputElement).value)}
              />
            </td>
            <td>
              <input
                type="number"
                value={range.max}
                oninput={(event) => setRange(index, 'max', (event.currentTarget as HTMLInputElement).value)}
              />
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}

{#if field.transformationRule?.type === 'categorical_mapping'}
  <h3>Value mapping <Explain text={help.mapping} tip /></h3>
  <Explain text={help.mapping} />
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Value in GIS</th>
          <th>Becomes</th>
        </tr>
      </thead>
      <tbody>
        {#each field.transformationRule.categoricalGroups || [] as group, index}
          <tr>
            <td>{group.sourceValues.join(', ')}</td>
            <td>
              <Select
                value={group.groupLabel}
                options={field.options.map((option) => ({ value: option, label: option }))}
                ariaLabel={`${group.sourceValues.join(', ')} becomes`}
                onChange={(value) => setGroup(index, value)}
              />
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}

<style>
  .field-grid {
    align-items: end;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 16px;
    margin-bottom: 16px;
  }

  label {
    display: flex;
    flex-direction: column;
    gap: 6px;
    font-size: 13px;
  }

  h3 {
    margin: var(--space-2) 0 var(--space-2);
    font-size: var(--text-md);
    font-weight: 600;
  }

  .table-wrap {
    overflow: auto;
    margin-bottom: 16px;
  }

  /* Inputs inside rule tables shrink to their cell instead of forcing a scrollbar. */
  td input {
    width: 100%;
    min-width: 0;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
  }

  th,
  td {
    border-bottom: 1px solid var(--border);
    padding: 10px;
    text-align: left;
  }

  th {
    font-size: var(--text-xs);
    font-weight: 500;
    color: var(--text-muted);
  }
</style>

export type MultiSelectOption = {
  description?: string;
  disabled?: boolean;
  keywords?: readonly string[];
  label: string;
  meta?: string;
  value: string;
};

export function filterMultiSelectOptions(
  options: readonly MultiSelectOption[],
  query: string,
) {
  const normalizedQuery = query.trim().toLocaleLowerCase();
  if (!normalizedQuery) return [...options];
  return options.filter((option) => [
    option.label,
    option.description ?? "",
    option.meta ?? "",
    ...(option.keywords ?? []),
  ].join(" ").toLocaleLowerCase().includes(normalizedQuery));
}

export function sortMultiSelectOptions(
  options: readonly MultiSelectOption[],
  locale?: string,
) {
  return [...options].sort((left, right) => left.label.localeCompare(
    right.label,
    locale,
    { numeric: true, sensitivity: "base" },
  ));
}

export function isMultiSelectOptionDisabled(
  option: MultiSelectOption,
  selectedValues: readonly string[],
  maxSelected?: number,
): boolean {
  const selected = selectedValues.includes(option.value);
  return Boolean(
    !selected
      && (option.disabled
        || (maxSelected !== undefined && selectedValues.length >= maxSelected)),
  );
}

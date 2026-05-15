import type { Provider } from "@/api";

export interface ProviderModelOption {
  providerId: string;
  providerName: string;
  model: string;
  value: string;
  label: string;
}

export function providerModelValue(provider: Provider, model: string): string {
  return `${provider.name}/${model}`;
}

export function providerModelOptions(providers: Provider[]): ProviderModelOption[] {
  return providers.flatMap((provider) =>
    provider.available_models.map((model) => {
      const value = providerModelValue(provider, model);
      return {
        providerId: provider.id,
        providerName: provider.name,
        model,
        value,
        label: value,
      };
    })
  );
}

export function providerScopedModelOptions(provider: Provider | null): ProviderModelOption[] {
  return provider ? providerModelOptions([provider]) : [];
}

export function resolveProviderByModelValue(
  providers: Provider[],
  modelValue: string | null | undefined
): ProviderModelOption | null {
  if (!modelValue) return null;
  return providerModelOptions(providers).find((option) => option.value === modelValue) ?? null;
}

export function resolveModelSelection(
  providers: Provider[],
  model: string | null | undefined,
  providerId: string | null | undefined
): ProviderModelOption | null {
  if (!model) return null;
  const options = providerModelOptions(providers);
  const exact = options.find((option) => option.value === model);
  if (exact) return exact;
  if (providerId) {
    const sameProvider = options.find((option) => option.providerId === providerId && option.model === model);
    if (sameProvider) return sameProvider;
  }
  const byModel = options.filter((option) => option.model === model);
  if (byModel.length === 1) return byModel[0];
  return null;
}

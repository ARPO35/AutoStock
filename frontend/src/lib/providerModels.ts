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

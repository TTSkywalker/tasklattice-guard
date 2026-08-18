{{- define "tali-guard.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "tali-guard.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "tali-guard.workloadName" -}}
{{- default "tali-guard" .Values.workloadNameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "tali-guard.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "tali-guard.labels" -}}
helm.sh/chart: {{ include "tali-guard.chart" . }}
{{ include "tali-guard.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: tali
{{- end }}

{{- define "tali-guard.selectorLabels" -}}
app.kubernetes.io/name: {{ include "tali-guard.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "tali-guard.workloadSelectorLabels" -}}
app.kubernetes.io/name: tali
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: guard
{{- end }}

{{- define "tali-guard.workloadLabels" -}}
helm.sh/chart: {{ include "tali-guard.chart" . }}
{{ include "tali-guard.workloadSelectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: tali
{{- end }}

{{- define "tali-guard.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "tali-guard.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{- define "tali-guard.nvidiaSecretName" -}}
{{- default (printf "%s-nvidia" (include "tali-guard.fullname" .)) .Values.evaluators.nvidia.existingSecret }}
{{- end }}

{{- define "tali-guard.deepseekSecretName" -}}
{{- default (printf "%s-deepseek" (include "tali-guard.fullname" .)) .Values.controlPlaneAgent.deepseek.existingSecret }}
{{- end }}

{{- define "tali-guard.playgroundChatSecretName" -}}
{{- default (printf "%s-playground-chat" (include "tali-guard.fullname" .)) .Values.playgroundChat.existingSecret }}
{{- end }}

{{- define "tali-guard.automatedReasoningSecretName" -}}
{{- default (printf "%s-automated-reasoning" (include "tali-guard.fullname" .)) .Values.evaluators.automatedReasoning.existingSecret }}
{{- end }}

{{- define "tali-guard.jailbreakDetectionSecretName" -}}
{{- default (printf "%s-jailbreak-detection" (include "tali-guard.fullname" .)) .Values.evaluators.jailbreakDetection.existingSecret }}
{{- end }}

{{- define "tali-guard.runtimeLogSecretName" -}}
{{- default (printf "%s-runtime-log" (include "tali-guard.fullname" .)) .Values.runtimeLogging.existingSecret }}
{{- end }}

{{- define "tali-guard.persistenceClaimName" -}}
{{- default (include "tali-guard.workloadName" .) .Values.persistence.existingClaim }}
{{- end }}

{{- define "tali-guard.validateValues" -}}
{{- if and (gt (int .Values.replicaCount) 1) (not (or .Values.database.url .Values.database.existingSecret)) }}
{{- fail "database.url or database.existingSecret is required when replicaCount is greater than 1" }}
{{- end }}
{{- if and .Values.database.url .Values.database.existingSecret }}
{{- fail "set either database.url or database.existingSecret, not both" }}
{{- end }}
{{- if and .Values.evaluators.nvidia.apiKey .Values.evaluators.nvidia.existingSecret }}
{{- fail "set either evaluators.nvidia.apiKey or evaluators.nvidia.existingSecret, not both" }}
{{- end }}
{{- if and .Values.playgroundChat.apiKey .Values.playgroundChat.existingSecret }}
{{- fail "set either playgroundChat.apiKey or playgroundChat.existingSecret, not both" }}
{{- end }}
{{- if ne (empty .Values.playgroundChat.baseUrl) (empty .Values.playgroundChat.model) }}
{{- fail "playgroundChat.baseUrl and playgroundChat.model must be configured together" }}
{{- end }}
{{- if and (or .Values.playgroundChat.baseUrl .Values.playgroundChat.model) (not (or .Values.playgroundChat.apiKey .Values.playgroundChat.existingSecret)) }}
{{- fail "a Playground chat credential is required when playgroundChat is configured" }}
{{- end }}
{{- if and (or .Values.playgroundChat.apiKey .Values.playgroundChat.existingSecret) (not (and .Values.playgroundChat.baseUrl .Values.playgroundChat.model)) }}
{{- fail "playgroundChat.baseUrl and playgroundChat.model are required when a Playground chat credential is configured" }}
{{- end }}
{{- if and .Values.evaluators.automatedReasoning.apiKey .Values.evaluators.automatedReasoning.existingSecret }}
{{- fail "set either evaluators.automatedReasoning.apiKey or evaluators.automatedReasoning.existingSecret, not both" }}
{{- end }}
{{- if and (or .Values.evaluators.automatedReasoning.apiKey .Values.evaluators.automatedReasoning.existingSecret) (not .Values.evaluators.automatedReasoning.endpointUrl) }}
{{- fail "evaluators.automatedReasoning.endpointUrl is required when an Automated Reasoning credential is configured" }}
{{- end }}
{{- if and .Values.evaluators.automatedReasoning.endpointUrl (not (or .Values.evaluators.automatedReasoning.apiKey .Values.evaluators.automatedReasoning.existingSecret)) }}
{{- fail "an Automated Reasoning credential is required when evaluators.automatedReasoning.endpointUrl is configured" }}
{{- end }}
{{- if and .Values.evaluators.jailbreakDetection.apiKey .Values.evaluators.jailbreakDetection.existingSecret }}
{{- fail "set either evaluators.jailbreakDetection.apiKey or evaluators.jailbreakDetection.existingSecret, not both" }}
{{- end }}
{{- if and (or .Values.evaluators.jailbreakDetection.apiKey .Values.evaluators.jailbreakDetection.existingSecret) (not .Values.evaluators.jailbreakDetection.nimBaseUrl) }}
{{- fail "evaluators.jailbreakDetection.nimBaseUrl is required when a Jailbreak Detection credential is configured" }}
{{- end }}
{{- if and .Values.evaluators.jailbreakDetection.nimBaseUrl (not (regexMatch "^https?://" .Values.evaluators.jailbreakDetection.nimBaseUrl)) }}
{{- fail "evaluators.jailbreakDetection.nimBaseUrl must be an HTTP(S) URL" }}
{{- end }}
{{- if lt (int .Values.observability.runtimeP95BudgetMs) 1 }}
{{- fail "observability.runtimeP95BudgetMs must be positive" }}
{{- end }}
{{- if lt (int .Values.observability.runtimeP99BudgetMs) (int .Values.observability.runtimeP95BudgetMs) }}
{{- fail "observability.runtimeP99BudgetMs must be at least runtimeP95BudgetMs" }}
{{- end }}
{{- if lt (int .Values.observability.maxConcurrencyPerGuardrail) 1 }}
{{- fail "observability.maxConcurrencyPerGuardrail must be positive" }}
{{- end }}
{{- if and .Values.observability.openTelemetry.enabled (not .Values.observability.openTelemetry.endpoint) }}
{{- fail "observability.openTelemetry.endpoint is required when OpenTelemetry is enabled" }}
{{- end }}
{{- if and .Values.observability.openTelemetry.endpoint (not (regexMatch "^https?://" .Values.observability.openTelemetry.endpoint)) }}
{{- fail "observability.openTelemetry.endpoint must be an HTTP(S) URL" }}
{{- end }}
{{- if and .Values.controlPlaneAgent.deepseek.apiKey .Values.controlPlaneAgent.deepseek.existingSecret }}
{{- fail "set either controlPlaneAgent.deepseek.apiKey or controlPlaneAgent.deepseek.existingSecret, not both" }}
{{- end }}
{{- if and (or .Values.controlPlaneAgent.deepseek.apiKey .Values.controlPlaneAgent.deepseek.existingSecret) (not .Values.controlPlaneAgent.deepseek.baseUrl) }}
{{- fail "controlPlaneAgent.deepseek.baseUrl is required when a DeepSeek credential is configured" }}
{{- end }}
{{- if and (or .Values.controlPlaneAgent.deepseek.apiKey .Values.controlPlaneAgent.deepseek.existingSecret) (not .Values.controlPlaneAgent.deepseek.model) }}
{{- fail "controlPlaneAgent.deepseek.model is required when a DeepSeek credential is configured" }}
{{- end }}
{{- if and (or .Values.evaluators.nvidia.contentSafetyModel .Values.evaluators.nvidia.topicControlModel .Values.evaluators.nvidia.groundingModel) (not .Values.evaluators.nvidia.baseUrl) }}
{{- fail "evaluators.nvidia.baseUrl is required when an NVIDIA evaluator model is configured" }}
{{- end }}
{{- end }}

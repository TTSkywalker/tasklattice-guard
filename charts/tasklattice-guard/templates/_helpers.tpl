{{- define "tasklattice-guard.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "tasklattice-guard.fullname" -}}
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

{{- define "tasklattice-guard.workloadName" -}}
{{- default "tali-guard" .Values.workloadNameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "tasklattice-guard.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "tasklattice-guard.labels" -}}
helm.sh/chart: {{ include "tasklattice-guard.chart" . }}
{{ include "tasklattice-guard.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: tali
{{- end }}

{{- define "tasklattice-guard.selectorLabels" -}}
app.kubernetes.io/name: {{ include "tasklattice-guard.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "tasklattice-guard.workloadSelectorLabels" -}}
app.kubernetes.io/name: tali
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: guard
{{- end }}

{{- define "tasklattice-guard.workloadLabels" -}}
helm.sh/chart: {{ include "tasklattice-guard.chart" . }}
{{ include "tasklattice-guard.workloadSelectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: tali
{{- end }}

{{- define "tasklattice-guard.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "tasklattice-guard.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{- define "tasklattice-guard.nvidiaSecretName" -}}
{{- default (printf "%s-nvidia" (include "tasklattice-guard.fullname" .)) .Values.evaluators.nvidia.existingSecret }}
{{- end }}

{{- define "tasklattice-guard.deepseekSecretName" -}}
{{- default (printf "%s-deepseek" (include "tasklattice-guard.fullname" .)) .Values.controlPlaneAgent.deepseek.existingSecret }}
{{- end }}

{{- define "tasklattice-guard.deepJudgeSecretName" -}}
{{- default (printf "%s-deep-judge" (include "tasklattice-guard.fullname" .)) .Values.evaluators.deepJudge.existingSecret }}
{{- end }}

{{- define "tasklattice-guard.automatedReasoningSecretName" -}}
{{- default (printf "%s-automated-reasoning" (include "tasklattice-guard.fullname" .)) .Values.evaluators.automatedReasoning.existingSecret }}
{{- end }}

{{- define "tasklattice-guard.jailbreakDetectionSecretName" -}}
{{- default (printf "%s-jailbreak-detection" (include "tasklattice-guard.fullname" .)) .Values.evaluators.jailbreakDetection.existingSecret }}
{{- end }}

{{- define "tasklattice-guard.persistenceClaimName" -}}
{{- default (include "tasklattice-guard.workloadName" .) .Values.persistence.existingClaim }}
{{- end }}

{{- define "tasklattice-guard.validateValues" -}}
{{- if ne (int .Values.replicaCount) 1 }}
{{- fail "replicaCount must be 1 while TaskLattice Guard uses SQLite" }}
{{- end }}
{{- if and .Values.evaluators.nvidia.apiKey .Values.evaluators.nvidia.existingSecret }}
{{- fail "set either evaluators.nvidia.apiKey or evaluators.nvidia.existingSecret, not both" }}
{{- end }}
{{- if and .Values.evaluators.deepJudge.apiKey .Values.evaluators.deepJudge.existingSecret }}
{{- fail "set either evaluators.deepJudge.apiKey or evaluators.deepJudge.existingSecret, not both" }}
{{- end }}
{{- if ne (empty .Values.evaluators.deepJudge.baseUrl) (empty .Values.evaluators.deepJudge.model) }}
{{- fail "evaluators.deepJudge.baseUrl and evaluators.deepJudge.model must be configured together" }}
{{- end }}
{{- if and (or .Values.evaluators.deepJudge.baseUrl .Values.evaluators.deepJudge.model) (not (or .Values.evaluators.deepJudge.apiKey .Values.evaluators.deepJudge.existingSecret)) }}
{{- fail "a runtime Policy Judge credential is required when evaluators.deepJudge is configured" }}
{{- end }}
{{- if and (or .Values.evaluators.deepJudge.apiKey .Values.evaluators.deepJudge.existingSecret) (not (and .Values.evaluators.deepJudge.baseUrl .Values.evaluators.deepJudge.model)) }}
{{- fail "evaluators.deepJudge.baseUrl and evaluators.deepJudge.model are required when a runtime Policy Judge credential is configured" }}
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

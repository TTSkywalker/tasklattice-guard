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

{{- define "tasklattice-guard.persistenceClaimName" -}}
{{- default (include "tasklattice-guard.fullname" .) .Values.persistence.existingClaim }}
{{- end }}

{{- define "tasklattice-guard.validateValues" -}}
{{- if ne (int .Values.replicaCount) 1 }}
{{- fail "replicaCount must be 1 while TaskLattice Guard uses SQLite" }}
{{- end }}
{{- if and .Values.evaluators.nvidia.apiKey .Values.evaluators.nvidia.existingSecret }}
{{- fail "set either evaluators.nvidia.apiKey or evaluators.nvidia.existingSecret, not both" }}
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
{{- if and (or .Values.evaluators.nvidia.contentSafetyModel .Values.evaluators.nvidia.topicControlModel) (not .Values.evaluators.nvidia.baseUrl) }}
{{- fail "evaluators.nvidia.baseUrl is required when an NVIDIA evaluator model is configured" }}
{{- end }}
{{- end }}

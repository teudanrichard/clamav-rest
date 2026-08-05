{{- define "clamav-rest.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- define "clamav-rest.fullname" -}}
{{- if .Values.fullnameOverride }}{{ .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}{{ else }}{{ printf "%s-%s" .Release.Name (include "clamav-rest.name" .) | trunc 63 | trimSuffix "-" }}{{ end }}
{{- end }}
{{- define "clamav-rest.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ include "clamav-rest.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}
{{- define "clamav-rest.selectorLabels" -}}
app.kubernetes.io/name: {{ include "clamav-rest.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
{{- define "clamav-rest.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}{{ default (include "clamav-rest.fullname" .) .Values.serviceAccount.name }}{{ else }}{{ default "default" .Values.serviceAccount.name }}{{ end }}
{{- end }}
{{- define "clamav-rest.image" -}}
{{- if .Values.image.digest }}{{ .Values.image.repository }}@{{ .Values.image.digest }}{{ else }}{{ .Values.image.repository }}:{{ default .Chart.AppVersion .Values.image.tag }}{{ end }}
{{- end }}
{{- define "clamav-rest.clamavImage" -}}
{{- if .Values.clamav.image.digest }}{{ .Values.clamav.image.repository }}@{{ .Values.clamav.image.digest }}{{ else }}{{ .Values.clamav.image.repository }}:{{ default "stable" .Values.clamav.image.tag }}{{ end }}
{{- end }}

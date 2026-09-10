{{- define "prama.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "prama.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "prama.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "prama.labels" -}}
app.kubernetes.io/name: {{ include "prama.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "prama.selectorLabels" -}}
app.kubernetes.io/name: {{ include "prama.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Refuse rather than default. Both of these produce a deployment that looks
installed and is wrong: a generated secret means forgeable sessions, and two
SQLite writers means corruption.
*/}}
{{- define "prama.validate" -}}
{{- if and (not .Values.existingSecret) (not .Values.createSecretFrom) -}}
{{- fail "prama: set existingSecret (or createSecretFrom for a non-production install). There is no default session secret, because a default means every installation shares a key that is public in this chart." -}}
{{- end -}}
{{- if and (eq .Values.database.dialect "sqlite") (gt (int .Values.replicaCount) 1) -}}
{{- fail "prama: sqlite with replicaCount > 1 is corruption, not high availability. Two pods writing one file will interleave. Use database.dialect=postgres, or set replicaCount=1." -}}
{{- end -}}
{{- if and (eq .Values.database.dialect "postgres") (not .Values.database.postgres.host) -}}
{{- fail "prama: database.dialect=postgres needs database.postgres.host." -}}
{{- end -}}
{{- end -}}

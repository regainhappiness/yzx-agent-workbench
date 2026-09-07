import type { Message } from '../types/api'

const KNOWLEDGE_INSTRUCTION = '请根据以下知识库内容回答用户问题。如果知识库内容不足以回答，请如实说明。'
const KNOWLEDGE_HEADER = '--- 知识库检索结果 ---'
const LEGACY_QUERY_MARKER = /\r?\n---\r?\n用户问题:\s*/g

export function visibleUserMessageContent(content: string): string {
  const normalized = content.trimStart()
  if (!normalized.startsWith(KNOWLEDGE_INSTRUCTION) || !normalized.includes(KNOWLEDGE_HEADER)) {
    return content
  }

  const markers = Array.from(normalized.matchAll(LEGACY_QUERY_MARKER))
  const marker = markers.at(-1)
  if (marker?.index === undefined) return content

  return normalized.slice(marker.index + marker[0].length).trim()
}

export function normalizeVisibleMessage(message: Message): Message {
  if (message.role !== 'user') return message
  return { ...message, content: visibleUserMessageContent(message.content) }
}

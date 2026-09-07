import {
  PhChatCircleDots as ChatCircleDots,
  PhGraph as GraphIcon,
} from '@phosphor-icons/vue'
import type { Component } from 'vue'

export interface AgentDefinition {
  id: string
  name: string
  shortName: string
  description: string
  routeName: string
  icon: Component
  capabilities: string[]
}

export const agents: AgentDefinition[] = [
  {
    id: 'chat',
    name: 'Chat Agent',
    shortName: '对话',
    description: '结合私有与共享知识库，完成检索增强问答。',
    routeName: 'chat',
    icon: ChatCircleDots,
    capabilities: ['多轮会话', '流式回答', 'RAG 检索'],
  },
  {
    id: 'multi-agent',
    name: 'Multi-Agent',
    shortName: '多智能体',
    description: '层级 Plan-and-Solve 编排：主智能体规划调度，子智能体分工执行。',
    routeName: 'multi-agent',
    icon: GraphIcon,
    capabilities: ['任务编排', '多Agent协作', '分级规划执行'],
  },
]

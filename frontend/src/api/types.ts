/** Short names for the generated OpenAPI schemas (src/api/schema.d.ts — do not edit that). */
import type { components } from './schema'

type Schemas = components['schemas']

export type Agent = Schemas['AgentOut']
export type AgentListItem = Schemas['AgentListItem']
export type AgentRef = Schemas['AgentRef']
export type Badge = Schemas['BadgeOut']
export type BadgeState = Badge['state']
export type TicketRow = Schemas['TicketRow']
export type TicketDetail = Schemas['TicketDetail']
export type Ticket = Schemas['TicketOut']
export type TicketStatus = Ticket['status']
export type Priority = Ticket['priority']
export type TargetStatus = Schemas['TargetStatusOut']
export type Message = Schemas['MessageOut']
export type Note = Schemas['NoteOut']
export type AuditEvent = Schemas['EventOut']
export type TicketCreateIn = Schemas['TicketCreateIn']
export type TicketCreated = Schemas['TicketCreatedOut']
export type LateRow = Schemas['LateRowOut']
export type Holiday = Schemas['HolidayOut']
export type HolidayIn = Schemas['HolidayIn']
export type VerifyResult = Schemas['VerifyOut']
export type CustomerTicket = Schemas['CustomerTicketOut']
export type CustomerMessage = Schemas['CustomerMessageOut']
export type CustomerWrite = Schemas['CustomerWriteOut']
export type PublicTicketIn = Schemas['PublicTicketIn']
export type PublicTicketCreated = Schemas['PublicTicketCreated']

/** The list views (D-034), from the generated query type. */
export type View = NonNullable<
  NonNullable<import('./schema').operations['list_tickets_api_agent_tickets_get']['parameters']['query']>['view']
>

/** allowed_actions values the server sends (app/domain/tickets.py ACTIONS). */
export type Action =
  | 'claim' | 'release' | 'assign' | 'reply' | 'reply_and_wait' | 'note' | 'resolve'
  | 'change_priority'

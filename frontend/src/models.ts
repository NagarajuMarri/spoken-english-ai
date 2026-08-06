export type TutorGender = "female" | "male";
export interface Tutor { tutor_id:string; display_name:string; gender:TutorGender; avatar_profile:string; voice_profile:string; accent:"Indian English"; teaching_style:string; animation_profile:string; prompt_profile:string; vocabulary_profile:string; enabled:boolean }
export interface TokenPair { access_token:string; refresh_token:string; token_type:"bearer"; expires_in:number }
export interface Account { id:string; learner_id:string; email:string; status:string }
export interface TutorPreference { learner_id:string; tutor:Tutor; telugu_explanations_enabled:boolean }
export interface Dashboard { learner_id:string; completed_sessions:number; current_streak_days:number; total_practice_minutes:number; preferred_tutor_id:string; subscription_tier:string; subscription_status:string }
export interface AiTurn { tutor_message:string; next_question:string; correction_explanation?:string; vocabulary_suggestions:string[]; telugu_explanation?:string }
export type AppRoute = "/"|"/pricing"|"/privacy"|"/terms"|"/refunds"|"/support"|"/faq"|"/login"|"/register"|"/onboarding"|"/app/dashboard"|"/app/daily-lesson"|"/app/conversation"|"/app/progress"|"/app/settings";

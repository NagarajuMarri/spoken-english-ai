export type AvatarState="IDLE"|"LISTENING"|"PROCESSING"|"THINKING"|"SPEAKING"|"ENCOURAGING"|"CORRECTING"|"ERROR"|"PAUSED";
const active:AvatarState[]=["LISTENING","PROCESSING","THINKING","SPEAKING","ENCOURAGING","CORRECTING"];
export const transitions:Record<AvatarState,readonly AvatarState[]>={
 IDLE:["LISTENING","PROCESSING","THINKING","SPEAKING","ERROR"],LISTENING:["PROCESSING","ERROR","PAUSED"],PROCESSING:["THINKING","ERROR","PAUSED"],THINKING:["SPEAKING","ERROR","PAUSED"],SPEAKING:["IDLE","ENCOURAGING","CORRECTING","ERROR","PAUSED"],ENCOURAGING:["IDLE","ERROR","PAUSED"],CORRECTING:["IDLE","ERROR","PAUSED"],ERROR:["IDLE"],PAUSED:["IDLE",...active]
};
export interface AvatarMachine{state:AvatarState;pausedFrom?:AvatarState}
export function transition(machine:AvatarMachine,next:AvatarState):AvatarMachine{if(!transitions[machine.state].includes(next))throw new Error(`Invalid avatar transition: ${machine.state} -> ${next}`);return next==="PAUSED"?{state:next,pausedFrom:machine.state}:{state:next}}
export function resume(machine:AvatarMachine):AvatarMachine{return machine.state==="PAUSED"?transition(machine,machine.pausedFrom??"IDLE"):machine}

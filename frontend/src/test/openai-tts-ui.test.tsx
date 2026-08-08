import{beforeEach,expect,it,vi}from"vitest";
import{fireEvent,render,screen,waitFor}from"@testing-library/react";
import userEvent from"@testing-library/user-event";
import{api}from"../api/client";
import type{TutorSpeech}from"../models";
import{RouterProvider}from"../routes/router";
import{ConversationScreen}from"../screens/ExperienceScreens";
import{TutorAudioPlayer}from"../voice/TutorAudioPlayer";
import{account,ananya}from"./fixtures";

const firstSpeech: TutorSpeech={blob:new Blob([new Uint8Array(64)],{type:"audio/mpeg"}),provider:"openai",model:"gpt-4o-mini-tts",voice:"marin",cacheStatus:"MISS",inputCharacters:48,providerRequests:1,usageClassification:"CHARACTERS_AND_BYTES_PROVIDER_TOKEN_USAGE_UNAVAILABLE"};
const secondSpeech: TutorSpeech={...firstSpeech,blob:new Blob([new Uint8Array(80)],{type:"audio/mpeg"}),voice:"cedar"};
let play:ReturnType<typeof vi.spyOn>;
let pause:ReturnType<typeof vi.spyOn>;
let load:ReturnType<typeof vi.spyOn>;

beforeEach(()=>{
 play=vi.spyOn(HTMLMediaElement.prototype,"play").mockResolvedValue(undefined);
 pause=vi.spyOn(HTMLMediaElement.prototype,"pause").mockImplementation(()=>undefined);
 load=vi.spyOn(HTMLMediaElement.prototype,"load").mockImplementation(()=>undefined);
 Object.defineProperty(URL,"createObjectURL",{configurable:true,value:vi.fn().mockReturnValueOnce("blob:first").mockReturnValueOnce("blob:second")});
 Object.defineProperty(URL,"revokeObjectURL",{configurable:true,value:vi.fn()});
});
it("plays valid OpenAI audio and exposes start end mute stop and replay controls",async()=>{
 render(<TutorAudioPlayer speech={firstSpeech} spokenText="You are improving. What happened next?"/>);
 await waitFor(()=>expect(play).toHaveBeenCalledTimes(1));
 expect(screen.getByText(/Provider: openai · Model: gpt-4o-mini-tts · Voice: marin/)).toBeVisible();
 const player=screen.getByLabelText(/Tutor audio for/);
 fireEvent.play(player);
 expect(screen.getByRole("status")).toHaveTextContent("Tutor voice is playing");
 fireEvent.ended(player);
 expect(screen.getByRole("status")).toHaveTextContent("Tutor voice finished");
 await userEvent.click(screen.getByRole("button",{name:"Mute"}));
 expect(player).toHaveProperty("muted",true);
 expect(screen.getByRole("button",{name:"Unmute"})).toHaveAttribute("aria-pressed","true");
 await userEvent.click(screen.getByRole("button",{name:"Stop"}));
 expect(pause).toHaveBeenCalled();
 expect(screen.getByRole("status")).toHaveTextContent("stopped");
 await userEvent.click(screen.getByRole("button",{name:"Replay"}));
 expect(play).toHaveBeenCalledTimes(2);
 expect(load).toHaveBeenCalled();
});

it("handles Chrome autoplay blocking with an explicit user play path",async()=>{
 play.mockRejectedValueOnce(new DOMException("blocked","NotAllowedError")).mockResolvedValueOnce(undefined);
 render(<TutorAudioPlayer speech={firstSpeech} spokenText="Tutor response"/>);
 expect(await screen.findByRole("status")).toHaveTextContent("Chrome blocked autoplay");
 await userEvent.click(screen.getByRole("button",{name:"Play tutor voice"}));
 await waitFor(()=>expect(play).toHaveBeenCalledTimes(2));
});

it("cancels the prior source and plays the second consecutive response once",async()=>{
 const{rerender}=render(<TutorAudioPlayer speech={firstSpeech} spokenText="First response"/>);
 await waitFor(()=>expect(play).toHaveBeenCalledTimes(1));
 rerender(<TutorAudioPlayer speech={secondSpeech} spokenText="Second response"/>);
 await waitFor(()=>expect(play).toHaveBeenCalledTimes(2));
 expect(pause).toHaveBeenCalled();
 expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:first");
 expect(screen.getByText(/Voice: cedar/)).toBeVisible();
});

it("retrieves OpenAI speech for the exact visible tutor turn without browser synthesis fallback",async()=>{
 vi.spyOn(api,"conversation").mockResolvedValue({id:"conversation-feature-5"});
 vi.spyOn(api,"turn").mockResolvedValue({turn_id:"ai-turn-feature-5",tutor_message:"You are improving.",next_question:"What happened next?",vocabulary_suggestions:[]});
 vi.spyOn(api,"speech").mockResolvedValue(firstSpeech);
 const browserSpeak=vi.fn();
 Object.defineProperty(window,"speechSynthesis",{configurable:true,value:{speak:browserSpeak}});
 render(<RouterProvider><ConversationScreen account={account} tutor={ananya} telugu={false}/></RouterProvider>);
 await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
 await userEvent.type(screen.getByLabelText("Your message"),"I studied today.");
 await userEvent.click(screen.getByRole("button",{name:"Send"}));
 expect(await screen.findByText("Ananya: You are improving. What happened next?")).toBeVisible();
 expect(api.speech).toHaveBeenCalledWith("conversation-feature-5","ai-turn-feature-5");
 expect(await screen.findByText(/Provider: openai/)).toBeVisible();
 expect(browserSpeak).not.toHaveBeenCalled();
});

it("keeps tutor text usable when TTS fails and offers an explicit audio-only retry",async()=>{
 vi.spyOn(api,"conversation").mockResolvedValue({id:"conversation-feature-5-error"});
 vi.spyOn(api,"turn").mockResolvedValue({turn_id:"ai-turn-feature-5-error",tutor_message:"Your text answer is safe.",next_question:"Would you like to retry audio?",vocabulary_suggestions:[]});
 vi.spyOn(api,"speech").mockRejectedValueOnce(new Error("Tutor voice timed out. Try audio again.")).mockResolvedValueOnce(firstSpeech);
 render(<RouterProvider><ConversationScreen account={account} tutor={ananya} telugu={false}/></RouterProvider>);
 await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
 await userEvent.type(screen.getByLabelText("Your message"),"Hello tutor.");
 await userEvent.click(screen.getByRole("button",{name:"Send"}));
 expect(await screen.findByText(/Your text answer is safe/)).toBeVisible();
 expect(await screen.findByRole("alert")).toHaveTextContent("Tutor voice timed out");
 expect(screen.getByLabelText("Your message")).toBeEnabled();
 await userEvent.click(screen.getByRole("button",{name:"Retry OpenAI voice"}));
 expect(await screen.findByText(/Provider: openai/)).toBeVisible();
 expect(api.turn).toHaveBeenCalledTimes(1);
 expect(api.speech).toHaveBeenCalledTimes(2);
});

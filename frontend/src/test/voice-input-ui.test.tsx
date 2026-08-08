import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "../api/client";
import { RouterProvider } from "../routes/router";
import { ConversationScreen } from "../screens/ExperienceScreens";
import { account, ananya } from "./fixtures";

class Recorder {
  static isTypeSupported=(type:string)=>type.startsWith("audio/webm");
  state:RecordingState="inactive";
  mimeType="audio/webm;codecs=opus";
  ondataavailable:((event:BlobEvent)=>void)|null=null;
  onerror:(()=>void)|null=null;
  onstop:(()=>void)|null=null;
  constructor(_stream:MediaStream,options?:MediaRecorderOptions){if(options?.mimeType)this.mimeType=options.mimeType}
  start(){this.state="recording"}
  stop(){
    this.state="inactive";
    this.ondataavailable?.({data:new Blob([new Uint8Array([1,2,3,4,5])],{type:this.mimeType})}as BlobEvent);
    this.onstop?.();
  }
}

const stream={getTracks:()=>[{stop:vi.fn()}]}as unknown as MediaStream;

beforeEach(()=>{
  Object.defineProperty(window,"isSecureContext",{configurable:true,value:true});
  Object.defineProperty(window,"MediaRecorder",{configurable:true,value:Recorder});
  Object.defineProperty(navigator,"mediaDevices",{configurable:true,value:{getUserMedia:vi.fn().mockResolvedValue(stream)}});
  Object.defineProperty(navigator,"permissions",{configurable:true,value:{query:vi.fn().mockResolvedValue({state:"prompt",addEventListener:vi.fn(),removeEventListener:vi.fn()})}});
  vi.spyOn(api,"conversation").mockResolvedValue({id:"conversation-voice"});
  vi.spyOn(api,"transcribe").mockResolvedValue({transcript:"I practise English every morning.",detected_language:"en",duration_ms:500,size_bytes:5});
  vi.spyOn(api,"turn").mockResolvedValue({turn_id:"voice-input-turn",tutor_message:"Thank you.",next_question:"What next?",vocabulary_suggestions:[]});
  vi.spyOn(api,"speech").mockRejectedValue(new Error("Audio is outside this STT-only test."));
});

describe("voice input customer journey",()=>{
  it("moves captured bytes through STT into visible learner text and the conversation pipeline",async()=>{
    render(<RouterProvider><ConversationScreen account={account} tutor={ananya} languageMode="ENGLISH"/></RouterProvider>);
    await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
    await userEvent.click(screen.getByRole("checkbox",{name:/consent to voice processing/i}));
    await userEvent.click(screen.getByRole("button",{name:"Start microphone"}));
    expect(screen.getByText(/Microphone: recording/)).toBeVisible();
    await waitFor(()=>expect(screen.getByLabelText(/tutor status: listening/)).toHaveAttribute("data-state", "LISTENING"));
    await userEvent.click(screen.getByRole("button",{name:"Stop and transcribe"}));
    await waitFor(()=>expect(api.transcribe).toHaveBeenCalledOnce());
    const capture=vi.mocked(api.transcribe).mock.calls[0][1];
    expect(capture.blob.size).toBeGreaterThan(0);
    expect(capture.blob.type).toContain("audio/webm");
    expect(await screen.findByLabelText("Recognized speech")).toHaveTextContent("I practise English every morning.");
    expect(screen.getByText("You: I practise English every morning.")).toBeVisible();
    expect(api.turn).toHaveBeenCalledWith(
      "conversation-voice",
      "I practise English every morning.",
      "ENGLISH",
      expect.any(String),
      { detectedLanguage: "en" },
    );
  });

  it("shows a safe STT error and does not submit an invented learner message",async()=>{
    vi.mocked(api.transcribe).mockRejectedValue(new ApiError(422,"No clear speech was detected."));
    render(<RouterProvider><ConversationScreen account={account} tutor={ananya} languageMode="ENGLISH"/></RouterProvider>);
    await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
    await userEvent.click(screen.getByRole("checkbox",{name:/consent to voice processing/i}));
    await userEvent.click(screen.getByRole("button",{name:"Start microphone"}));
    await userEvent.click(screen.getByRole("button",{name:"Stop and transcribe"}));
    expect(await screen.findByRole("alert")).toHaveTextContent("No clear speech was detected.");
    expect(api.turn).not.toHaveBeenCalled();
  });
});

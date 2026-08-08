import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { RouterProvider } from "../routes/router";
import { ConversationScreen } from "../screens/ExperienceScreens";
import { TutorPicker } from "../screens/TutorPicker";
import { account, ananya, arjun, preference } from "./fixtures";

describe("native Telugu language review capability",()=>{
  beforeEach(()=>{
    vi.spyOn(api,"tutors").mockResolvedValue([ananya,arjun]);
    vi.spyOn(api,"savePreference").mockResolvedValue(preference);
  });

  it("offers three separated modes and saves the learner-selected mode",async()=>{
    render(<RouterProvider><TutorPicker/></RouterProvider>);
    await userEvent.click(await screen.findByRole("radio",{name:/Ananya/}));
    expect(screen.getByDisplayValue("ENGLISH")).toBeVisible();
    expect(screen.getByRole("radio",{name:/English \+ Telugu explanation/})).toBeVisible();
    expect(screen.getByRole("radio",{name:/Telugu-dominant explanation/})).toBeVisible();
    await userEvent.click(screen.getByRole("radio",{name:/Telugu-dominant explanation/}));
    expect(screen.getByText(/every response is reviewed for natural teacher-like Telugu/)).toBeVisible();
    await userEvent.click(screen.getByRole("button",{name:"Continue with my tutor"}));
    expect(api.savePreference).toHaveBeenCalledWith("ananya","TELUGU_DOMINANT");
  });

  it("shows customer-facing review evidence before requesting accepted TTS",async()=>{
    vi.spyOn(HTMLMediaElement.prototype,"play").mockResolvedValue(undefined);
    vi.spyOn(HTMLMediaElement.prototype,"pause").mockImplementation(()=>undefined);
    vi.spyOn(HTMLMediaElement.prototype,"load").mockImplementation(()=>undefined);
    Object.defineProperty(URL,"createObjectURL",{configurable:true,value:vi.fn().mockReturnValue("blob:reviewed-telugu")});
    Object.defineProperty(URL,"revokeObjectURL",{configurable:true,value:vi.fn()});
    vi.spyOn(api,"conversation").mockResolvedValue({id:"conversation-language-review"});
    vi.spyOn(api,"turn").mockResolvedValue({
      turn_id:"turn-language-review",
      tutor_message:"చాలా బాగా ప్రయత్నించారు. ఈ sentence ని ఇంకోసారి చెప్పండి.",
      next_question:"ఇప్పుడు అదే sentence చెప్పగలరా?",
      corrected_sentence:"I went to the office yesterday.",
      correction_explanation:"ఈ sentence లో tense మాత్రమే మార్చాలి.",
      vocabulary_suggestions:[],
      telugu_explanation:"ఈ sentence లో tense మాత్రమే మార్చాలి.",
      language_mode:"TELUGU_DOMINANT",
      review_changed:true,
      review_reason_code:"NATURALIZED_TELUGU",
      preserved_learning_terms:["sentence","tense"],
      expression_hint:"CORRECTIVE",
      spoken_text:"మీ meaning clear గా ఉంది. Correct sentence: I went to the office yesterday. ఈ sentence లో tense మాత్రమే మార్చాలి. ఇప్పుడు corrected sentence ని ఒకసారి చెప్పండి.",
      coaching_mode:"RETRY_REQUIRED",
      coaching_state:"WAITING_FOR_RETRY",
      retry_of_turn_id:null,
    });
    vi.spyOn(api,"speech").mockResolvedValue({
      blob:new Blob([new Uint8Array(64)],{type:"audio/mpeg"}),provider:"openai",
      model:"gpt-4o-mini-tts",voice:"marin",cacheStatus:"MISS",inputCharacters:80,
      providerRequests:1,usageClassification:"provider-token-usage-unavailable",
    });

    render(<RouterProvider><ConversationScreen account={account} tutor={ananya} languageMode="TELUGU_DOMINANT"/></RouterProvider>);
    await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
    await userEvent.type(screen.getByLabelText("Your message"),"I go office yesterday");
    await userEvent.click(screen.getByRole("button",{name:"Send"}));
    expect(await screen.findByText("Native Telugu quality review")).toBeVisible();
    expect(screen.getByText(/NATURALIZED_TELUGU/)).toBeVisible();
    expect(screen.getByText(/sentence, tense/)).toBeVisible();
    expect(screen.getByText(/Ananya: మీ meaning clear గా ఉంది\. Correct sentence: I went to the office yesterday\./)).toBeVisible();
    expect(screen.getAllByText("ఈ sentence లో tense మాత్రమే మార్చాలి.")).toHaveLength(2);
    expect(api.speech).toHaveBeenCalledWith("conversation-language-review","turn-language-review");
  });
});

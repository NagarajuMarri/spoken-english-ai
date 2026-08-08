import {render,screen,waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect,it,vi} from "vitest";
import {ApiError,api} from "../api/client";
import {RouterProvider} from "../routes/router";
import {ConversationScreen} from "../screens/ExperienceScreens";
import {account,ananya} from "./fixtures";

it("shows a provider-safe tutor failure and allows the learner to retry",async()=>{
  vi.spyOn(api,"conversation").mockResolvedValue({id:"conversation-1"});
  vi.spyOn(api,"turn")
    .mockRejectedValueOnce(new ApiError(503,"The tutor could not connect. Retry this turn.","llm_connection_error",true,"req-1"))
    .mockResolvedValueOnce({tutor_message:"Recovered response.",next_question:"What happened next?",vocabulary_suggestions:[]});
  render(<RouterProvider><ConversationScreen account={account} tutor={ananya} telugu={false}/></RouterProvider>);
  await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
  await userEvent.type(screen.getByLabelText("Your message"),"Please help me practise.");
  await userEvent.click(screen.getByRole("button",{name:"Send"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("The tutor could not connect");
  expect(screen.getByLabelText("Your message")).toHaveValue("Please help me practise.");
  expect(screen.getAllByText("You: Please help me practise.")).toHaveLength(1);
  const firstKey=vi.mocked(api.turn).mock.calls[0][3];
  await userEvent.click(screen.getByRole("button",{name:"Retry tutor response"}));
  expect(await screen.findByText(/Recovered response/)).toBeVisible();
  expect(vi.mocked(api.turn).mock.calls[1][3]).toBe(firstKey);
  expect(screen.getAllByText("You: Please help me practise.")).toHaveLength(1);
  expect(vi.mocked(api.turn)).toHaveBeenCalledTimes(2);
  expect(screen.getByLabelText("Your message")).toBeEnabled();
});

it("does not offer automatic retry for a non-transient provider response",async()=>{
  vi.spyOn(api,"conversation").mockResolvedValue({id:"conversation-2"});
  vi.spyOn(api,"turn").mockRejectedValue(
    new ApiError(502,"The tutor response could not be validated. Send the turn again.","llm_schema_validation_failed",false,"req-2"),
  );
  render(<RouterProvider><ConversationScreen account={account} tutor={ananya} telugu={false}/></RouterProvider>);
  await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
  await userEvent.type(screen.getByLabelText("Your message"),"Please check this.");
  await userEvent.click(screen.getByRole("button",{name:"Send"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("could not be validated");
  expect(screen.queryByRole("button",{name:"Retry tutor response"})).not.toBeInTheDocument();
});

it("allows a safe same-turn retry after an incomplete OpenAI response",async()=>{
  vi.spyOn(api,"conversation").mockResolvedValue({id:"conversation-3"});
  vi.spyOn(api,"turn")
    .mockRejectedValueOnce(new ApiError(
      502,
      "The tutor response ended before it was complete. Retry this turn safely.",
      "llm_incomplete_response",
      true,
      "req-3",
    ))
    .mockResolvedValueOnce({
      tutor_message:"I can continue now.",
      next_question:"What would you like to discuss?",
      vocabulary_suggestions:[],
    });
  render(<RouterProvider><ConversationScreen account={account} tutor={ananya} telugu={false}/></RouterProvider>);
  await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
  await userEvent.type(screen.getByLabelText("Your message"),"Please continue.");
  await userEvent.click(screen.getByRole("button",{name:"Send"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("ended before it was complete");
  const firstKey=vi.mocked(api.turn).mock.calls[0][3];
  await userEvent.click(screen.getByRole("button",{name:"Retry tutor response"}));
  expect(await screen.findByText(/I can continue now/)).toBeVisible();
  expect(vi.mocked(api.turn).mock.calls[1][3]).toBe(firstKey);
  expect(screen.getAllByText("You: Please continue.")).toHaveLength(1);
});

import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";

export default [{ignores:["dist"]},{files:["**/*.{js,jsx}"],languageOptions:{ecmaVersion:2022,globals:globals.browser,parserOptions:{ecmaVersion:"latest",ecmaFeatures:{jsx:true},sourceType:"module"}},plugins:{"react-hooks":reactHooks},rules:{...js.configs.recommended.rules,...reactHooks.configs.recommended.rules}}];

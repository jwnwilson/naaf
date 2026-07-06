import { FormField, Textarea, TextInput } from "../../components/ui";

export interface ProjectFormValues {
  name: string;
  repoUrl: string;
  description: string;
}

interface Props {
  values: ProjectFormValues;
  onChange: (patch: Partial<ProjectFormValues>) => void;
}

export function ProjectFormFields({ values, onChange }: Props) {
  return (
    <>
      <FormField label="Name">
        <TextInput
          aria-label="Name"
          value={values.name}
          onChange={(e) => onChange({ name: e.target.value })}
          autoFocus
        />
      </FormField>
      <FormField label="Repo URL">
        <TextInput
          aria-label="Repo URL"
          value={values.repoUrl}
          placeholder="https://github.com/org/repo"
          onChange={(e) => onChange({ repoUrl: e.target.value })}
        />
      </FormField>
      <FormField label="Description">
        <Textarea
          aria-label="Description"
          value={values.description}
          onChange={(e) => onChange({ description: e.target.value })}
        />
      </FormField>
    </>
  );
}

import type { Program, Subject, Workspace } from "./lib/contracts";
import type { CloudStatus, DocumentFile } from "./lib/workflow-api";

// Fictional, memory-only review data. No student workspace or Drive is read.
export const uid = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
export const JAVA_ID = uid(1);
export const PREVIEW_TIME = "2026-11-15T09:20:00.000Z";
export const SAMPLE_CODE = `import java.util.Scanner;

public class PalindromeCheck {
    public static void main(String[] args) {
        Scanner input = new Scanner(System.in);
        System.out.print("Enter a number: ");
        int number = input.nextInt();
        int original = number;
        int reversed = 0;

        while (number != 0) {
            reversed = reversed * 10 + number % 10;
            number /= 10;
        }

        System.out.println(original == reversed
            ? "Palindrome" : "Not a palindrome");
        input.close();
    }
}`;

const titles = [
  "Find the largest of three numbers", "Generate the Fibonacci series",
  "Check whether a number is a palindrome", "Find prime numbers in a range",
  "Sort an array using bubble sort", "Multiply two matrices",
  "Demonstrate single inheritance", "Overload constructors in a class",
  "Implement an interface", "Handle arithmetic exceptions",
  "Read and write a text file", "Create a user-defined package",
  "Demonstrate method overriding", "Use an abstract class",
  "Implement a stack", "Implement a queue", "Search an array",
  "Sort an array using insertion sort", "Find the frequency of characters",
  "Reverse the words in a sentence", "Implement a linked list",
  "Demonstrate multithreading", "Synchronise access to a shared resource",
  "Use a generic class", "Work with an ArrayList",
  "Sort objects using a comparator", "Read command-line arguments",
  "Create a custom exception", "Store and retrieve student details",
];

export function makeWorkspace(): Workspace {
  const programs: Program[] = titles.map((title, i) => ({
    id: uid(100 + i), number: i + 1, title,
    question: `Write a Java program to ${title.charAt(0).toLowerCase() + title.slice(1)}.`,
    createdAt: PREVIEW_TIME,
    updatedAt: i === 2 ? PREVIEW_TIME : "2026-11-14T10:00:00.000Z",
    trashedAt: null,
    sources: i < 16 ? [{
      id: uid(1000 + i), name: i === 2 ? "PalindromeCheck.java" : `Program${i + 1}.java`,
      role: "Main code", code: SAMPLE_CODE, include: true,
    }] : [],
    outputs: i < 8 ? [
      { id: uid(2000 + i), kind: "text", name: "Test case 1", text: "Enter a number: 121\nPalindrome", include: true },
      ...(i === 2 ? [{ id: uid(2500 + i), kind: "text" as const, name: "Test case 2", text: "Enter a number: 123\nNot a palindrome", include: true }] : []),
    ] : [],
    outputMayBeStale: false,
  }));
  programs.push({
    ...programs[0]!, id: uid(900), number: 30, title: "Practice: number patterns",
    sources: [], outputs: [], trashedAt: "2026-11-14T12:10:00.000Z",
  });
  const java: Subject = {
    id: JAVA_ID, name: "Java Programming Lab", semester: 3, courseCode: "CSL 203",
    updatedAt: PREVIEW_TIME, trashedAt: null, programs, fields: [], sourceRoles: ["Main code"],
    template: {
      id: uid(10), name: "Java record template.docx", dataBase64: "",
      placeholders: ["NO", "TITLE", "CODE", "OUTPUT"], reviewed: true, uploadedAt: PREVIEW_TIME,
      mappings: {
        NO: { field: "number", required: true }, TITLE: { field: "title", required: true },
        CODE: { field: "source:Main code", required: true }, OUTPUT: { field: "output", required: true },
      },
    },
    index: { enabled: true, title: "Index", columns: [
      { id: uid(11), label: "No.", field: "number" },
      { id: uid(12), label: "Experiment", field: "title" },
    ] },
  };
  return { schemaVersion: 1, subjects: [
    java,
    { id: uid(2), name: "Data Structures Lab", semester: 3, courseCode: "CSL 201", programs: [], template: null, updatedAt: PREVIEW_TIME, trashedAt: null },
    { id: uid(3), name: "Web Technology Lab", semester: 4, courseCode: "CSL 204", programs: [], template: null, updatedAt: PREVIEW_TIME, trashedAt: null },
  ] };
}

export let previewCloud: CloudStatus = {
  configured: true, connected: true, account: { name: "Student account", email: "student@example.edu" },
  state: "synced", busy: false, pending: false, lastSyncAt: PREVIEW_TIME,
  revision: "preview-revision", syncedRevision: "preview-revision",
};
export function setPreviewCloud(change: Partial<CloudStatus>) {
  previewCloud = { ...previewCloud, ...change };
  return previewCloud;
}

export const previewDocuments: DocumentFile[] = [
  { id: "preview-doc-1", name: "Java-combined-2026-11-15T091000000Z-34b65c5e.docx", format: "docx", subjectId: JAVA_ID, programIds: [uid(100), uid(101), uid(102)], createdAt: "2026-11-15T09:10:00.000Z", byteLength: 185420 },
  { id: "preview-doc-2", name: "Java-combined-2026-11-15T091000000Z-34b65c5e.pdf", format: "pdf", subjectId: JAVA_ID, programIds: [uid(100), uid(101), uid(102)], createdAt: "2026-11-15T09:10:00.000Z", byteLength: 234510 },
  { id: "preview-doc-3", name: "Java-program-03-2026-11-14T153000000Z-9b83d71a.docx", format: "docx", subjectId: JAVA_ID, programIds: [uid(102)], createdAt: "2026-11-14T15:30:00.000Z", byteLength: 68480 },
];
